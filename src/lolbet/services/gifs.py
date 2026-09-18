"""Choix du GIF qui accompagne un récap, quand la situation le mérite.

Un GIF à chaque partie deviendrait du bruit. Seules quelques situations en
déclenchent un — série de défaites, gros feed, pire joueur, rétrogradation,
victoire portée, série de victoires — et un seul GIF part par récap, pour le
joueur dont la situation est la plus marquante.

Deux sources, sans clé d'abord :

* la liste curée de ``gif_lines.py``, toujours disponible ;
* Tenor, si ``LOLBET_TENOR_API_KEY`` est renseignée : une clé Google Cloud
  gratuite, sans facturation. Ça apporte de la variété ; une panne de Tenor
  retombe sur la liste curée sans rien casser.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

import httpx

from ..logging_conf import get_logger
from .gif_lines import CAPTIONS, GIFS, TENOR_QUERIES

log = get_logger(__name__)

# Catégorie de vanne -> situation GIF. Une catégorie absente n'envoie rien.
# L'ordre de ce tuple est aussi la priorité entre joueurs d'un même récap :
# le premier qui correspond emporte le GIF.
CATEGORY_TO_SITUATION: tuple[tuple[str, str], ...] = (
    ("streak_lost", "losing_streak"),
    ("demoted", "demoted"),
    ("record_deaths", "fed"),
    ("repeat_lvp", "worst"),
    ("worst_lost", "worst"),
    ("fed_lost", "fed"),
    ("lp_crash", "demoted"),
    ("streak_won", "winning_streak"),
    ("worst_won", "lucky_win"),
    ("fed_won", "lucky_win"),
    ("bad_won", "lucky_win"),
)
_SITUATION_OF = dict(CATEGORY_TO_SITUATION)
_PRIORITY = {category: index for index, (category, _) in enumerate(CATEGORY_TO_SITUATION)}

TENOR_ENDPOINT = "https://tenor.googleapis.com/v2/search"
TENOR_TTL_SECONDS = 3600.0
TENOR_LIMIT = 20


def situation_for(category: str) -> str | None:
    return _SITUATION_OF.get(category)


def priority_of(category: str) -> int:
    """Plus petit = plus marquant. Les catégories sans GIF passent en dernier."""
    return _PRIORITY.get(category, len(_PRIORITY))


@dataclass(frozen=True, slots=True)
class Gif:
    situation: str
    url: str
    caption: str


def caption_for(situation: str, mention: str, rng: random.Random) -> str:
    lines = CAPTIONS.get(situation) or ("{mention}",)
    return rng.choice(lines).format(mention=mention)


class GifPicker:
    """Tire un GIF pour une situation. Sans clé Tenor, liste curée seulement."""

    def __init__(self, api_key: str | None = None, *, http: httpx.AsyncClient | None = None) -> None:
        self._api_key = (api_key or "").strip()
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(8.0))
        # situation -> (expire, urls). Tenor n'est interrogé qu'une fois par
        # heure et par situation, pas une fois par partie.
        self._cache: dict[str, tuple[float, list[str]]] = {}

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @property
    def uses_tenor(self) -> bool:
        return bool(self._api_key)

    async def pick(self, situation: str, rng: random.Random) -> str | None:
        curated = list(GIFS.get(situation) or ())
        remote = await self._from_tenor(situation) if self.uses_tenor else []
        # Les deux sources se mélangent : la liste curée reste toujours dans
        # le tirage, pour que les blagues internes ne se noient pas.
        pool = curated + remote
        if not pool:
            return None
        return rng.choice(pool)

    async def _from_tenor(self, situation: str) -> list[str]:
        query = TENOR_QUERIES.get(situation)
        if not query:
            return []
        cached = self._cache.get(situation)
        now = time.monotonic()
        if cached is not None and cached[0] > now:
            return cached[1]

        try:
            response = await self._http.get(
                TENOR_ENDPOINT,
                params={
                    "q": query,
                    "key": self._api_key,
                    "limit": TENOR_LIMIT,
                    "media_filter": "gif",
                    "contentfilter": "medium",
                    "client_key": "lolbet",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Tenor en panne ou clé refusée : on note, on retombe sur la
            # liste curée, et on ne réessaie pas avant l'expiration.
            log.warning("gifs.tenor_failed", situation=situation, error=str(exc))
            self._cache[situation] = (now + TENOR_TTL_SECONDS, [])
            return []

        urls: list[str] = []
        for result in payload.get("results") or []:
            formats = result.get("media_formats") or {}
            entry = formats.get("gif") or formats.get("mediumgif") or {}
            url = entry.get("url")
            if isinstance(url, str) and url.startswith("https://"):
                urls.append(url)
        self._cache[situation] = (now + TENOR_TTL_SECONDS, urls)
        return urls
