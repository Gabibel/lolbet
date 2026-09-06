"""Turn a SPECTATOR-V5 payload into a :class:`GameCard`.

Phase 1 (``enrich=False``) uses nothing but the spectator payload, so the
announcement goes out with zero extra API calls and betting can open at once.
Phase 2 (``enrich=True``) adds rank, mastery and level for all ten players -
30 requests, all of them cached, fired concurrently and throttled by the
shared limiter.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from ..logging_conf import get_logger
from ..riot.client import RiotClient
from ..riot.ddragon import DDragon
from ..riot.rank import solo_queue_rank
from ..utils import from_epoch_ms
from .embeds import GameCard, PlayerCard

log = get_logger(__name__)


def parse_riot_id(raw: str | None) -> tuple[str, str]:
    if not raw:
        return "Unknown", ""
    name, _, tag = raw.partition("#")
    return name or "Unknown", tag


def spectator_participants(spectator: dict[str, Any]) -> list[dict[str, Any]]:
    return list(spectator.get("participants") or [])


def find_team_id(spectator: dict[str, Any], puuids: set[str]) -> int:
    for participant in spectator_participants(spectator):
        if participant.get("puuid") in puuids:
            return int(participant.get("teamId") or 100)
    return 100


def base_card(
    spectator: dict[str, Any],
    *,
    platform: str,
    riot_game_id: str,
    tracked: dict[str, int],
    lock_at: datetime | None = None,
) -> GameCard:
    """Phase-1 card: everything the spectator payload already tells us."""
    players: list[PlayerCard] = []
    for participant in spectator_participants(spectator):
        puuid = str(participant.get("puuid") or "")
        name, tag = parse_riot_id(participant.get("riotId"))
        players.append(
            PlayerCard(
                puuid=puuid,
                riot_id=f"{name}#{tag}" if tag else name,
                champion_id=int(participant.get("championId") or 0),
                team_id=int(participant.get("teamId") or 100),
                spell1_id=int(participant.get("spell1Id") or 0),
                spell2_id=int(participant.get("spell2Id") or 0),
                is_tracked=puuid in tracked,
                discord_id=tracked.get(puuid),
            )
        )

    return GameCard(
        riot_game_id=riot_game_id,
        platform=platform,
        queue_id=int(spectator.get("gameQueueConfigId") or 0),
        tracked_team_id=find_team_id(spectator, set(tracked)),
        players=players,
        started_at=from_epoch_ms(spectator.get("gameStartTime")),
        lock_at=lock_at,
        enriched=False,
    )


async def enrich_card(
    card: GameCard,
    client: RiotClient,
    *,
    cached_only: bool = False,
) -> GameCard:
    """Fill in rank, mastery and summoner level for all ten players."""
    platform = card.platform

    async def load(player: PlayerCard) -> None:
        if not player.puuid:
            return
        entries, summoner, mastery = await asyncio.gather(
            client.get_league_entries(player.puuid, platform, cached_only=cached_only),
            client.get_summoner(player.puuid, platform, cached_only=cached_only),
            client.get_champion_mastery(
                player.puuid, player.champion_id, platform, cached_only=cached_only
            ),
            return_exceptions=True,
        )
        if not isinstance(entries, BaseException):
            player.rank = solo_queue_rank(entries)
        if isinstance(summoner, dict):
            player.summoner_level = int(summoner.get("summonerLevel") or 0) or None
        if isinstance(mastery, dict):
            player.mastery_level = int(mastery.get("championLevel") or 0) or None
            player.mastery_points = int(mastery.get("championPoints") or 0)
            player.mastery_last_played = from_epoch_ms(mastery.get("lastPlayTime"))

    results = await asyncio.gather(
        *(load(player) for player in card.players), return_exceptions=True
    )
    for result in results:
        if isinstance(result, BaseException):
            log.warning("enrich.player_failed", error=str(result))

    card.enriched = any(
        p.rank is not None or p.summoner_level is not None or p.mastery_points is not None
        for p in card.players
    )
    return card


async def build_card(
    spectator: dict[str, Any],
    client: RiotClient,
    ddragon: DDragon,
    *,
    platform: str,
    riot_game_id: str,
    tracked: dict[str, int],
    lock_at: datetime | None = None,
    enrich: bool = False,
    cached_only: bool = False,
) -> GameCard:
    await ddragon.ensure_fresh()
    card = base_card(
        spectator,
        platform=platform,
        riot_game_id=riot_game_id,
        tracked=tracked,
        lock_at=lock_at,
    )
    if enrich:
        await enrich_card(card, client, cached_only=cached_only)
    return card
