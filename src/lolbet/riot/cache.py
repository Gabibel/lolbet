"""Per-endpoint TTL cache: in-memory dict, mirrored into SQLite.

The mirror exists so a restart starts warm. Without it, every reboot would
replay hundreds of ACCOUNT-V1 and SUMMONER-V4 lookups against a 100 req/2min
budget before the bot could do anything useful.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..logging_conf import get_logger
from ..models import ApiCacheEntry

log = get_logger(__name__)

DAY = 86_400.0
HOUR = 3_600.0

# TTL per endpoint. FOREVER is expressed as None.
TTL_ACCOUNT = 7 * DAY  # ACCOUNT-V1 riot id <-> puuid
TTL_SUMMONER = 7 * DAY  # SUMMONER-V4 level / profile icon
TTL_LEAGUE = 6 * HOUR  # LEAGUE-V4 tier / rank / LP
TTL_MASTERY = 1 * DAY  # CHAMPION-MASTERY-V4, keyed on (puuid, championId)
TTL_DDRAGON = 1 * DAY  # DDragon version + champion data
TTL_MATCH: float | None = None  # MATCH-V5 is immutable, keep forever

_MISS = object()


class TTLCache:
    """Async, coalescing TTL cache with optional SQLite persistence."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        *,
        clock: Callable[[], float] = time.time,
        persist: bool = True,
    ) -> None:
        self._mem: dict[str, tuple[float | None, Any]] = {}
        self._session_factory = session_factory
        self._clock = clock
        self._persist = persist and session_factory is not None
        self._locks: dict[str, asyncio.Lock] = {}

    # -- reads ------------------------------------------------------------

    async def get(self, key: str) -> Any | None:
        value = self._get_live(key)
        return None if value is _MISS else value

    def _get_live(self, key: str) -> Any:
        entry = self._mem.get(key)
        if entry is None:
            return _MISS
        expires_at, value = entry
        if expires_at is not None and expires_at <= self._clock():
            self._mem.pop(key, None)
            return _MISS
        return value

    def __contains__(self, key: str) -> bool:
        return self._get_live(key) is not _MISS

    # -- writes -----------------------------------------------------------

    async def set(self, key: str, value: Any, ttl: float | None) -> None:
        expires_at = None if ttl is None else self._clock() + ttl
        self._mem[key] = (expires_at, value)
        if self._persist:
            await self._write_through(key, value, expires_at)

    async def invalidate(self, key: str) -> None:
        self._mem.pop(key, None)
        if not self._persist:
            return
        assert self._session_factory is not None
        async with self._session_factory() as session:
            await session.execute(delete(ApiCacheEntry).where(ApiCacheEntry.key == key))
            await session.commit()

    async def get_or_set(
        self,
        key: str,
        ttl: float | None,
        producer: Callable[[], Any],
    ) -> Any:
        """Return the cached value, otherwise await ``producer`` once.

        Concurrent callers for the same key wait on a per-key lock instead of
        all firing the same request - this is what keeps five players in one
        game from triggering five identical lookups.
        """
        cached = self._get_live(key)
        if cached is not _MISS:
            return cached

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._get_live(key)
            if cached is not _MISS:
                return cached
            value = await producer()
            await self.set(key, value, ttl)
            return value
        # note: locks are pruned lazily by prune_locks() to bound memory

    def prune_locks(self) -> None:
        for key, lock in list(self._locks.items()):
            if not lock.locked():
                self._locks.pop(key, None)

    # -- persistence ------------------------------------------------------

    async def _write_through(self, key: str, value: Any, expires_at: float | None) -> None:
        assert self._session_factory is not None
        try:
            payload = json.dumps(value, separators=(",", ":"))
        except (TypeError, ValueError):
            log.warning("cache.unserialisable", key=key)
            return
        stmt = (
            sqlite_insert(ApiCacheEntry)
            .values(key=key, payload=payload, expires_at=expires_at, stored_at=self._clock())
            .on_conflict_do_update(
                index_elements=[ApiCacheEntry.key],
                set_={"payload": payload, "expires_at": expires_at, "stored_at": self._clock()},
            )
        )
        try:
            async with self._session_factory() as session:
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:  # cache writes must never break a command
            log.warning("cache.write_failed", key=key, error=str(exc))

    async def warm_from_disk(self) -> int:
        """Load every unexpired row back into memory. Called once at boot."""
        if not self._persist:
            return 0
        assert self._session_factory is not None
        now = self._clock()
        loaded = 0
        async with self._session_factory() as session:
            rows = (await session.execute(select(ApiCacheEntry))).scalars().all()
            for row in rows:
                if row.expires_at is not None and row.expires_at <= now:
                    continue
                try:
                    self._mem[row.key] = (row.expires_at, json.loads(row.payload))
                except ValueError:
                    continue
                loaded += 1
        log.info("cache.warmed", entries=loaded)
        return loaded

    async def purge_expired(self) -> int:
        """Drop expired rows from memory and disk."""
        now = self._clock()
        for key, (expires_at, _) in list(self._mem.items()):
            if expires_at is not None and expires_at <= now:
                self._mem.pop(key, None)
        self.prune_locks()
        if not self._persist:
            return 0
        assert self._session_factory is not None
        async with self._session_factory() as session:
            result = await session.execute(
                delete(ApiCacheEntry).where(
                    ApiCacheEntry.expires_at.is_not(None), ApiCacheEntry.expires_at <= now
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

    @property
    def size(self) -> int:
        return len(self._mem)
