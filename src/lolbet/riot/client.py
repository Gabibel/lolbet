"""Async Riot API client.

PUUID-based endpoints only. Riot removed the summonerId-based routes on
20 June 2025, so nothing here ever touches
``/lol/league/v4/entries/by-summoner/`` or ``/lol/summoner/v4/summoners/{id}``.

Every request goes through the shared rate limiter and the per-endpoint TTL
cache. The API key travels in the X-Riot-Token header and is never logged.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any
from urllib.parse import quote

import httpx

from ..config import PLATFORM_TO_REGION, Settings
from ..logging_conf import get_logger
from .cache import (
    TTL_ACCOUNT,
    TTL_LEAGUE,
    TTL_MASTERY,
    TTL_MATCH,
    TTL_SUMMONER,
    TTLCache,
)
from .ratelimit import RateLimiter

log = get_logger(__name__)

# Distinguishes "no 404 fallback given, so re-raise" from "the fallback is None".
_RAISE = object()


class RiotAPIError(Exception):
    def __init__(self, status: int, path: str, message: str = "") -> None:
        self.status = status
        self.path = path
        super().__init__(f"Riot API {status} on {path}{f': {message}' if message else ''}")


class RiotNotFound(RiotAPIError):
    """404 - for spectator this is the normal "not in a game" answer."""


class RiotUnauthorized(RiotAPIError):
    """401/403 - almost always an expired dev key."""


class RiotUnavailable(RiotAPIError):
    """5xx or a transport error that survived every retry."""


def normalise_platform(platform: str | None, default: str) -> str:
    value = (platform or default).strip().lower()
    return value if value in PLATFORM_TO_REGION else default


class RiotClient:
    def __init__(
        self,
        settings: Settings,
        cache: TTLCache,
        limiter: RateLimiter,
        *,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._limiter = limiter
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            headers={
                "X-Riot-Token": settings.riot_api_key,
                "Accept": "application/json",
                "User-Agent": "LoLBet/0.1 (+self-hosted)",
            },
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # -- plumbing ---------------------------------------------------------

    async def _request(self, url: str, path: str) -> httpx.Response | None:
        """One HTTP GET with rate limiting, 429 back-off and 5xx retries."""
        attempt = 0
        while True:
            async with self._limiter.slot():
                try:
                    response = await self._http.get(url)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt >= self._settings.max_retries:
                        raise RiotUnavailable(0, path, str(exc)) from exc
                    delay = self._backoff(attempt)
                    log.warning("riot.transport_retry", path=path, attempt=attempt, delay=delay)
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue

            status = response.status_code
            if status == 200:
                return response
            if status == 404:
                raise RiotNotFound(404, path)
            if status in (401, 403):
                raise RiotUnauthorized(status, path, "check LOLBET_RIOT_API_KEY")
            if status == 429:
                retry_after = self._retry_after(response)
                # Park the whole limiter, then wait it out. Never busy-retry.
                self._limiter.penalise(retry_after)
                if attempt >= self._settings.max_retries:
                    raise RiotUnavailable(429, path, "rate limited")
                attempt += 1
                await asyncio.sleep(retry_after)
                continue
            if 500 <= status < 600:
                if attempt >= self._settings.max_retries:
                    raise RiotUnavailable(status, path)
                delay = self._backoff(attempt)
                log.warning("riot.server_retry", path=path, status=status, delay=delay)
                attempt += 1
                await asyncio.sleep(delay)
                continue
            raise RiotAPIError(status, path, response.text[:200])

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        raw = response.headers.get("Retry-After")
        try:
            value = float(raw) if raw is not None else 1.0
        except ValueError:
            value = 1.0
        # Riot sometimes answers with 0; sleeping zero would be a busy loop.
        return max(1.0, min(value, 120.0))

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(8.0, 2**attempt) + random.uniform(0, 0.4)

    async def _get_json(
        self,
        url: str,
        path: str,
        *,
        cache_key: str | None,
        ttl: float | None,
        default_on_404: Any = _RAISE,
        cached_only: bool = False,
    ) -> Any:
        if cached_only:
            # Used by the debounced embed refresh: answer from the warm cache
            # or give up, but never spend quota just to redraw odds.
            return None if cache_key is None else await self._cache.get(cache_key)

        async def fetch() -> Any:
            try:
                response = await self._request(url, path)
            except RiotNotFound:
                if default_on_404 is _RAISE:
                    raise
                return default_on_404
            assert response is not None
            return response.json()

        if cache_key is None:
            return await fetch()
        return await self._cache.get_or_set(cache_key, ttl, fetch)

    # -- ACCOUNT-V1 (regional) --------------------------------------------

    async def get_account_by_riot_id(
        self, game_name: str, tag_line: str, platform: str
    ) -> dict[str, Any] | None:
        """Riot ID -> account (puuid). Cached 7 days."""
        platform = normalise_platform(platform, self._settings.default_platform)
        host = self._settings.region_host(platform)
        path = f"/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}"
        key = f"account:riot-id:{platform}:{game_name.strip().lower()}:{tag_line.strip().lower()}"
        return await self._get_json(
            host + path, "ACCOUNT-V1/by-riot-id", cache_key=key, ttl=TTL_ACCOUNT,
            default_on_404=None,
        )

    async def get_account_by_puuid(
        self, puuid: str, platform: str, *, cached_only: bool = False
    ) -> dict[str, Any] | None:
        """PUUID -> account, used to refresh a renamed Riot ID. Cached 7 days."""
        platform = normalise_platform(platform, self._settings.default_platform)
        host = self._settings.region_host(platform)
        path = f"/riot/account/v1/accounts/by-puuid/{quote(puuid)}"
        return await self._get_json(
            host + path,
            "ACCOUNT-V1/by-puuid",
            cache_key=f"account:puuid:{puuid}",
            ttl=TTL_ACCOUNT,
            default_on_404=None,
            cached_only=cached_only,
        )

    # -- SPECTATOR-V5 (platform) ------------------------------------------

    async def get_active_game(self, puuid: str, platform: str) -> dict[str, Any] | None:
        """Live game for a PUUID, or None when the player is not in one.

        Despite the path name this takes a PUUID. Never cached: a stale answer
        here would mean announcing a game that already ended.
        """
        platform = normalise_platform(platform, self._settings.default_platform)
        host = self._settings.platform_host(platform)
        path = f"/lol/spectator/v5/active-games/by-summoner/{quote(puuid)}"
        return await self._get_json(
            host + path, "SPECTATOR-V5", cache_key=None, ttl=None, default_on_404=None
        )

    # -- LEAGUE-V4 (platform) ---------------------------------------------

    async def get_league_entries(
        self, puuid: str, platform: str, *, cached_only: bool = False
    ) -> list[dict[str, Any]]:
        """Ranked entries by PUUID. Cached 6 hours."""
        platform = normalise_platform(platform, self._settings.default_platform)
        host = self._settings.platform_host(platform)
        path = f"/lol/league/v4/entries/by-puuid/{quote(puuid)}"
        entries = await self._get_json(
            host + path,
            "LEAGUE-V4/by-puuid",
            cache_key=f"league:{platform}:{puuid}",
            ttl=TTL_LEAGUE,
            default_on_404=[],
            cached_only=cached_only,
        )
        return entries or []

    async def refresh_league_entries(
        self, puuid: str, platform: str
    ) -> list[dict[str, Any]]:
        """Ranked entries, ignoring the 6h cache.

        Used right after a game: the cached value predates it, so it would
        report the rank the player had before winning or losing.
        """
        platform = normalise_platform(platform, self._settings.default_platform)
        await self._cache.invalidate(f"league:{platform}:{puuid}")
        return await self.get_league_entries(puuid, platform)

    # -- SUMMONER-V4 (platform) -------------------------------------------

    async def get_summoner(
        self, puuid: str, platform: str, *, cached_only: bool = False
    ) -> dict[str, Any] | None:
        """Level and profile icon. Cached 7 days."""
        platform = normalise_platform(platform, self._settings.default_platform)
        host = self._settings.platform_host(platform)
        path = f"/lol/summoner/v4/summoners/by-puuid/{quote(puuid)}"
        return await self._get_json(
            host + path,
            "SUMMONER-V4/by-puuid",
            cache_key=f"summoner:{platform}:{puuid}",
            ttl=TTL_SUMMONER,
            default_on_404=None,
            cached_only=cached_only,
        )

    # -- CHAMPION-MASTERY-V4 (platform) -----------------------------------

    async def get_champion_mastery(
        self, puuid: str, champion_id: int, platform: str, *, cached_only: bool = False
    ) -> dict[str, Any] | None:
        """Mastery for one champion. Cached 24h on (puuid, championId)."""
        platform = normalise_platform(platform, self._settings.default_platform)
        host = self._settings.platform_host(platform)
        path = (
            f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{quote(puuid)}"
            f"/by-champion/{int(champion_id)}"
        )
        return await self._get_json(
            host + path,
            "CHAMPION-MASTERY-V4",
            cache_key=f"mastery:{platform}:{puuid}:{champion_id}",
            ttl=TTL_MASTERY,
            default_on_404=None,
            cached_only=cached_only,
        )

    # -- MATCH-V5 (regional) ----------------------------------------------

    async def get_match(self, match_id: str, platform: str) -> dict[str, Any] | None:
        """Finished match. Cached forever - the payload is immutable."""
        platform = normalise_platform(platform, self._settings.default_platform)
        host = self._settings.region_host(platform)
        path = f"/lol/match/v5/matches/{quote(match_id)}"
        return await self._get_json(
            host + path,
            "MATCH-V5",
            cache_key=f"match:{match_id}",
            ttl=TTL_MATCH,
            default_on_404=None,
        )


def build_match_id(platform: str, game_id: int | str) -> str:
    """Spectator gives a bare gameId; MATCH-V5 wants ``EUW1_7123456789``."""
    return f"{platform.upper()}_{game_id}"
