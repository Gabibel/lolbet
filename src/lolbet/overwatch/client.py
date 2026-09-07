"""Client OverFast : l'API non officielle qui lit les profils Overwatch.

Blizzard n'expose aucune API Overwatch. OverFast lit la page de carrière
publique et la sert en JSON. C'est gratuit, open source et auto-hébergeable
en Docker, donc conforme à la contrainte du projet — mais ça reste du bon
vouloir d'un tiers : le client doit rester poli et supporter une panne.

Ce que l'API donne : la division et le palier par rôle. Ce qu'elle ne donne
pas, et qu'aucune API ne donne : le détail partie par partie, et la partie en
cours. C'est pour ça qu'il n'y a pas de paris Overwatch dans ce bot.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

import httpx

from ..config import Settings
from ..logging_conf import get_logger
from ..riot.cache import TTLCache
from ..riot.ratelimit import RateLimiter

log = get_logger(__name__)

# Le profil de carrière lui-même ne bouge qu'après une session de jeu, et
# OverFast le garde une heure de son côté. Rafraîchir plus souvent ne
# donnerait rien de neuf, juste du trafic chez eux.
TTL_OW_SUMMARY = 600.0
TTL_OW_SEARCH = 600.0

BATTLETAG_RE = re.compile(r"^(?P<name>[^\s#]{3,30})[#-](?P<discriminator>\d{4,7})$")


class OverFastError(Exception):
    def __init__(self, status: int, path: str, message: str = "") -> None:
        self.status = status
        self.path = path
        super().__init__(f"OverFast {status} sur {path}{f': {message}' if message else ''}")


class OwPlayerNotFound(OverFastError):
    """404 — le BattleTag n'existe pas, ou le profil est introuvable."""


class OwUnavailable(OverFastError):
    """5xx, timeout, ou une limite de débit qui a survécu aux tentatives."""


class InvalidBattleTag(ValueError):
    """Saisi par un humain, donc régulièrement faux."""


def normalise_battletag(value: str) -> str:
    """``Nom#1234`` ou ``Nom-1234`` → ``Nom#1234``. Lève si c'est autre chose."""
    candidate = (value or "").strip()
    match = BATTLETAG_RE.match(candidate)
    if match is None:
        raise InvalidBattleTag(
            "BattleTag attendu sous la forme « Pseudo#1234 »."
        )
    return f"{match['name']}#{match['discriminator']}"


def to_player_id(battletag: str) -> str:
    """Format attendu dans l'URL OverFast : ``Nom-1234``."""
    return quote(normalise_battletag(battletag).replace("#", "-"), safe="")


class OverFastClient:
    """Lectures seules, mises en cache, et volontairement peu bavardes."""

    def __init__(
        self,
        settings: Settings,
        cache: TTLCache,
        *,
        http: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache
        # L'instance publique limite au débit par seconde, tous points
        # d'entrée confondus. On reste très en dessous : quelques joueurs
        # relus toutes les quinze minutes.
        self._limiter = limiter or RateLimiter([(2, 1.0)], max_concurrency=2)
        self._base = settings.overfast_base_url.rstrip("/")
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            headers={
                "Accept": "application/json",
                "User-Agent": "LoLBet/0.1 (+self-hosted; suivi de rang entre amis)",
            },
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # -- plomberie --------------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._base}{path}"
        attempt = 0
        while True:
            async with self._limiter.slot():
                try:
                    response = await self._http.get(url, params=params)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt >= self._settings.max_retries:
                        raise OwUnavailable(0, path, str(exc)) from exc
                    attempt += 1
                    await asyncio.sleep(min(8.0, 2.0**attempt))
                    continue

            status = response.status_code
            if status == 200:
                return response.json()
            if status == 404:
                raise OwPlayerNotFound(404, path)
            if status == 429:
                # Jamais de réessai serré : on gare le limiteur et on attend.
                retry_after = _retry_after(response)
                self._limiter.penalise(retry_after)
                if attempt >= self._settings.max_retries:
                    raise OwUnavailable(429, path, "débit limité")
                attempt += 1
                await asyncio.sleep(retry_after)
                continue
            if status >= 500:
                if attempt >= self._settings.max_retries:
                    raise OwUnavailable(status, path, "OverFast indisponible")
                attempt += 1
                await asyncio.sleep(min(8.0, 2.0**attempt))
                continue
            raise OverFastError(status, path, response.text[:200])

    # -- lectures ---------------------------------------------------------

    async def get_summary(self, battletag: str) -> dict:
        """Résumé de profil : pseudo, avatar et rang par rôle."""
        player_id = to_player_id(battletag)
        key = f"ow:summary:{player_id}"
        return await self._cache.get_or_set(
            key, TTL_OW_SUMMARY, lambda: self._get(f"/players/{player_id}/summary")
        )

    async def refresh_summary(self, battletag: str) -> dict:
        """Comme ``get_summary`` mais en ignorant le cache.

        Utilisé par la boucle de suivi : lire une valeur vieille de dix
        minutes ferait manquer un changement de rang, ou pire, le ferait
        annoncer deux fois.
        """
        player_id = to_player_id(battletag)
        summary = await self._get(f"/players/{player_id}/summary")
        await self._cache.set(f"ow:summary:{player_id}", summary, TTL_OW_SUMMARY)
        return summary

    async def search(self, name: str) -> list[dict]:
        """Recherche par pseudo, pour retrouver un BattleTag mal orthographié."""
        payload = await self._cache.get_or_set(
            f"ow:search:{name.lower()}",
            TTL_OW_SEARCH,
            lambda: self._get("/players", params={"name": name}),
        )
        return list((payload or {}).get("results") or [])


def _retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After")
    try:
        return max(1.0, float(raw)) if raw else 5.0
    except ValueError:
        return 5.0
