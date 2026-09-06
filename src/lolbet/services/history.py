"""Historique des parties jouées et forme d'un joueur.

Les statistiques sont figées au moment du règlement : sans ça, l'historique et
les séries devraient être reconstruits depuis MATCH-V5 à chaque consultation,
ce qui coûterait du quota pour des données qui ne changent plus.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Bet, PlayerGameStat, TrackedGame, TrackedParticipant
from ..utils import utcnow
from .scoring import MatchScores

STREAK_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class PlayerForm:
    """Ce que l'historique dit d'un joueur, avant sa partie du moment."""

    games: int = 0
    wins: int = 0
    losses: int = 0
    # Positif = victoires d'affilée, négatif = défaites d'affilée.
    streak: int = 0
    worst_deaths: int = 0
    best_score: float = 0.0
    mvp_count: int = 0
    lvp_count: int = 0
    total_kills: int = 0
    total_deaths: int = 0
    total_assists: int = 0

    @property
    def is_new(self) -> bool:
        return self.games == 0

    @property
    def winrate(self) -> float | None:
        return (self.wins / self.games * 100) if self.games else None

    @property
    def avg_kda(self) -> float:
        return (self.total_kills + self.total_assists) / max(1, self.total_deaths)

    @property
    def losing_streak(self) -> int:
        return -self.streak if self.streak < 0 else 0

    @property
    def winning_streak(self) -> int:
        return self.streak if self.streak > 0 else 0


def _streak(results: list[bool]) -> int:
    """``results`` du plus récent au plus ancien. Renvoie la série en cours."""
    if not results:
        return 0
    first = results[0]
    length = 0
    for win in results:
        if win != first:
            break
        length += 1
    return length if first else -length


async def player_form(
    session: AsyncSession, guild_id: int, discord_id: int, *, limit: int = 100
) -> PlayerForm:
    """Forme d'un joueur d'après les parties déjà enregistrées."""
    rows = (
        (
            await session.execute(
                select(PlayerGameStat)
                .where(
                    PlayerGameStat.guild_id == guild_id,
                    PlayerGameStat.discord_id == discord_id,
                )
                .order_by(PlayerGameStat.played_at.desc(), PlayerGameStat.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return PlayerForm()

    return PlayerForm(
        games=len(rows),
        wins=sum(1 for r in rows if r.win),
        losses=sum(1 for r in rows if not r.win),
        streak=_streak([r.win for r in rows]),
        worst_deaths=max(r.deaths for r in rows),
        best_score=max(r.score for r in rows),
        mvp_count=sum(1 for r in rows if r.is_mvp),
        lvp_count=sum(1 for r in rows if r.is_lvp),
        total_kills=sum(r.kills for r in rows),
        total_deaths=sum(r.deaths for r in rows),
        total_assists=sum(r.assists for r in rows),
    )


async def record_game_stats(
    session: AsyncSession,
    game: TrackedGame,
    scores: MatchScores,
    participants: list[TrackedParticipant],
) -> list[PlayerGameStat]:
    """Fige les lignes de statistiques des joueurs suivis. Idempotent."""
    existing = set(
        (
            await session.execute(
                select(PlayerGameStat.puuid).where(PlayerGameStat.game_id == game.id)
            )
        )
        .scalars()
        .all()
    )

    mvp_puuid = scores.mvp.puuid if scores.mvp else None
    lvp_puuid = scores.worst.puuid if scores.worst else None
    now = utcnow()
    created: list[PlayerGameStat] = []

    for participant in participants:
        if participant.puuid in existing:
            continue
        score = scores.by_puuid(participant.puuid)
        if score is None:
            continue
        stat = PlayerGameStat(
            game_id=int(game.id or 0),
            guild_id=game.guild_id,
            discord_id=participant.discord_id,
            puuid=participant.puuid,
            riot_game_id=game.riot_game_id,
            queue_id=game.queue_id,
            duration_seconds=scores.duration_seconds,
            champion_id=score.champion_id,
            champion_name=score.champion_name,
            position=score.position,
            win=score.win,
            kills=score.kills,
            deaths=score.deaths,
            assists=score.assists,
            cs=score.cs,
            cs_per_min=round(score.cs_per_min, 2),
            damage=score.damage,
            gold=score.gold,
            vision_score=score.vision_score,
            score=score.score,
            is_mvp=participant.puuid == mvp_puuid,
            is_lvp=participant.puuid == lvp_puuid,
            played_at=now,
        )
        session.add(stat)
        created.append(stat)

    await session.flush()
    return created


async def recent_games(
    session: AsyncSession, guild_id: int, discord_id: int, limit: int = 10
) -> list[PlayerGameStat]:
    result = await session.execute(
        select(PlayerGameStat)
        .where(
            PlayerGameStat.guild_id == guild_id,
            PlayerGameStat.discord_id == discord_id,
        )
        .order_by(PlayerGameStat.played_at.desc(), PlayerGameStat.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def guild_recent_games(
    session: AsyncSession, guild_id: int, limit: int = 10
) -> list[PlayerGameStat]:
    result = await session.execute(
        select(PlayerGameStat)
        .where(PlayerGameStat.guild_id == guild_id)
        .order_by(PlayerGameStat.played_at.desc(), PlayerGameStat.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def settled_bets(
    session: AsyncSession, guild_id: int, user_id: int, limit: int = 10
) -> list[Bet]:
    """Paris réglés, du plus récent au plus ancien."""
    result = await session.execute(
        select(Bet)
        .where(
            Bet.guild_id == guild_id,
            Bet.user_id == user_id,
            Bet.settled_at.is_not(None),
        )
        .order_by(Bet.settled_at.desc(), Bet.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def bet_totals(session: AsyncSession, guild_id: int, user_id: int) -> dict[str, int]:
    """Meilleur et pire pari réglés, pour le profil."""
    row = (
        await session.execute(
            select(
                func.max(Bet.payout - Bet.amount),
                func.min(Bet.payout - Bet.amount),
                func.count(Bet.id),
            ).where(
                Bet.guild_id == guild_id,
                Bet.user_id == user_id,
                Bet.settled_at.is_not(None),
            )
        )
    ).one()
    best, worst, count = row
    return {
        "best": int(best or 0),
        "worst": int(worst or 0),
        "settled": int(count or 0),
    }
