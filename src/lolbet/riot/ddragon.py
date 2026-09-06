"""Data Dragon static data: champions, summoner spells, icons.

DDragon needs no API key, has no rate limit, and does not count against the
Riot quota - so these requests deliberately bypass the rate limiter. Fetched
at boot, held in memory, re-checked once a day.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from ..logging_conf import get_logger
from .cache import TTL_DDRAGON, TTLCache

log = get_logger(__name__)

BASE = "https://ddragon.leagueoflegends.com"
VERSIONS_URL = f"{BASE}/api/versions.json"

FALLBACK_VERSION = "14.24.1"


class DDragon:
    """Champion / spell / icon lookups, refreshed daily."""

    def __init__(
        self,
        cache: TTLCache,
        *,
        http: httpx.AsyncClient | None = None,
        locale: str = "en_US",
    ) -> None:
        self._cache = cache
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._locale = locale
        self._version: str = FALLBACK_VERSION
        self._champions_by_key: dict[int, dict[str, str]] = {}
        self._spells_by_key: dict[int, dict[str, str]] = {}
        self._checked_at: float = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @property
    def version(self) -> str:
        return self._version

    @property
    def ready(self) -> bool:
        return bool(self._champions_by_key)

    # -- fetching ---------------------------------------------------------

    async def _get(self, url: str, cache_key: str) -> Any:
        async def fetch() -> Any:
            response = await self._http.get(url)
            response.raise_for_status()
            return response.json()

        return await self._cache.get_or_set(cache_key, TTL_DDRAGON, fetch)

    async def refresh(self, *, force: bool = False) -> None:
        """Load version + champion + spell data. Safe to call repeatedly."""
        async with self._lock:
            if not force and self._checked_at and time.time() - self._checked_at < TTL_DDRAGON:
                return
            try:
                versions = await self._get(VERSIONS_URL, "ddragon:versions")
                if isinstance(versions, list) and versions:
                    self._version = str(versions[0])

                champions = await self._get(
                    f"{BASE}/cdn/{self._version}/data/{self._locale}/champion.json",
                    f"ddragon:champions:{self._version}:{self._locale}",
                )
                self._champions_by_key = {
                    int(entry["key"]): {
                        "id": entry["id"],
                        "name": entry["name"],
                        "image": entry.get("image", {}).get("full", f"{entry['id']}.png"),
                    }
                    for entry in (champions or {}).get("data", {}).values()
                    if entry.get("key", "").isdigit()
                }

                spells = await self._get(
                    f"{BASE}/cdn/{self._version}/data/{self._locale}/summoner.json",
                    f"ddragon:spells:{self._version}:{self._locale}",
                )
                self._spells_by_key = {
                    int(entry["key"]): {
                        "id": entry["id"],
                        "name": entry["name"],
                        "image": entry.get("image", {}).get("full", f"{entry['id']}.png"),
                    }
                    for entry in (spells or {}).get("data", {}).values()
                    if entry.get("key", "").isdigit()
                }

                self._checked_at = time.time()
                log.info(
                    "ddragon.loaded",
                    version=self._version,
                    champions=len(self._champions_by_key),
                    spells=len(self._spells_by_key),
                )
            except Exception as exc:
                # Static data is cosmetic; the bot stays usable without it.
                log.warning("ddragon.refresh_failed", error=str(exc))

    async def ensure_fresh(self) -> None:
        if not self.ready or time.time() - self._checked_at >= TTL_DDRAGON:
            await self.refresh()

    # -- lookups ----------------------------------------------------------

    def champion_name(self, champion_id: int) -> str:
        entry = self._champions_by_key.get(int(champion_id))
        return entry["name"] if entry else f"Champion {champion_id}"

    def champion_slug(self, champion_id: int) -> str | None:
        entry = self._champions_by_key.get(int(champion_id))
        return entry["id"] if entry else None

    def champion_icon_url(self, champion_id: int) -> str | None:
        entry = self._champions_by_key.get(int(champion_id))
        if not entry:
            return None
        return f"{BASE}/cdn/{self._version}/img/champion/{entry['image']}"

    def champion_splash_url(self, champion_id: int) -> str | None:
        slug = self.champion_slug(champion_id)
        if not slug:
            return None
        return f"{BASE}/cdn/img/champion/splash/{slug}_0.jpg"

    def spell_name(self, spell_id: int) -> str:
        entry = self._spells_by_key.get(int(spell_id))
        return entry["name"] if entry else f"Spell {spell_id}"

    def spell_icon_url(self, spell_id: int) -> str | None:
        entry = self._spells_by_key.get(int(spell_id))
        if not entry:
            return None
        return f"{BASE}/cdn/{self._version}/img/spell/{entry['image']}"

    def profile_icon_url(self, icon_id: int) -> str:
        return f"{BASE}/cdn/{self._version}/img/profileicon/{int(icon_id)}.png"
