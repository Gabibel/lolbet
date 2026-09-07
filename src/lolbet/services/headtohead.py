"""Face-à-face entre deux joueurs suivis.

Avec six inscrits, ce sont les rivalités deux à deux qui font vivre le
serveur. Deux comparaisons ici, qu'il ne faut pas confondre :

* la **forme générale**, calculée sur tout l'historique de chacun, même
  quand ils n'ont jamais joué ensemble ;
* le **face-à-face réel**, restreint aux parties où les deux étaient
  présents — la seule qui permette de dire « il te bat quand vous jouez
  ensemble ».
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PlayerGameStat, TrackedParticipant


@dataclass(frozen=True, slots=True)
class Side:
    """Le bilan d'un joueur sur l'ensemble comparé."""

    discord_id: int
    games: int = 0
    wins: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    mvp: int = 0
    lvp: int = 0
    score: float = 0.0

    @property
    def winrate(self) -> float | None:
        return (self.wins / self.games * 100) if self.games else None

    @property
    def kda(self) -> float:
        return (self.kills + self.assists) / max(1, self.deaths)

    @property
    def avg_score(self) -> float:
        return self.score / self.games if self.games else 0.0

    @property
    def avg_deaths(self) -> float:
        return self.deaths / self.games if self.games else 0.0


@dataclass(frozen=True, slots=True)
class HeadToHead:
    left: Side
    right: Side
    # Parties où les deux étaient présents.
    together: int = 0
    # Sur ces parties-là, combien chacun a fini devant l'autre au score.
    left_ahead: int = 0
    right_ahead: int = 0
    same_team: int = 0
    against: int = 0
    left_wins_against: int = 0
    right_wins_against: int = 0

    @property
    def has_shared_games(self) -> bool:
        return self.together > 0

    @property
    def leader(self) -> int | None:
        """Qui domine le face-à-face, ou None si c'est à égalité."""
        if self.left_ahead > self.right_ahead:
            return self.left.discord_id
        if self.right_ahead > self.left_ahead:
            return self.right.discord_id
        return None


def _side(discord_id: int, rows: list[PlayerGameStat]) -> Side:
    return Side(
        discord_id=discord_id,
        games=len(rows),
        wins=sum(1 for r in rows if r.win),
        kills=sum(r.kills for r in rows),
        deaths=sum(r.deaths for r in rows),
        assists=sum(r.assists for r in rows),
        cs=sum(r.cs for r in rows),
        mvp=sum(1 for r in rows if r.is_mvp),
        lvp=sum(1 for r in rows if r.is_lvp),
        score=sum(r.score for r in rows),
    )


async def _stats(
    session: AsyncSession, guild_id: int, discord_id: int
) -> list[PlayerGameStat]:
    rows = (
        (
            await session.execute(
                select(PlayerGameStat).where(
                    PlayerGameStat.guild_id == guild_id,
                    PlayerGameStat.discord_id == discord_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _teams(session: AsyncSession, game_ids: set[int]) -> dict[tuple[int, int], int]:
    """(game_id, discord_id) -> team_id, pour savoir qui était avec qui."""
    if not game_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(TrackedParticipant).where(
                    TrackedParticipant.game_id.in_(game_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    return {(row.game_id, row.discord_id): row.team_id for row in rows}


async def compare(
    session: AsyncSession, guild_id: int, left_id: int, right_id: int
) -> HeadToHead:
    """Compare deux joueurs, en général puis sur leurs parties communes."""
    left_rows = await _stats(session, guild_id, left_id)
    right_rows = await _stats(session, guild_id, right_id)

    by_game_left = {row.game_id: row for row in left_rows}
    by_game_right = {row.game_id: row for row in right_rows}
    shared = set(by_game_left) & set(by_game_right)

    teams = await _teams(session, shared)

    left_ahead = right_ahead = 0
    same_team = against = 0
    left_wins_against = right_wins_against = 0
    for game_id in shared:
        left_row, right_row = by_game_left[game_id], by_game_right[game_id]
        if left_row.score > right_row.score:
            left_ahead += 1
        elif right_row.score > left_row.score:
            right_ahead += 1

        left_team = teams.get((game_id, left_id))
        right_team = teams.get((game_id, right_id))
        if left_team is None or right_team is None:
            continue
        if left_team == right_team:
            same_team += 1
        else:
            against += 1
            # Dans un duel, un seul des deux peut avoir gagné.
            if left_row.win:
                left_wins_against += 1
            elif right_row.win:
                right_wins_against += 1

    return HeadToHead(
        left=_side(left_id, left_rows),
        right=_side(right_id, right_rows),
        together=len(shared),
        left_ahead=left_ahead,
        right_ahead=right_ahead,
        same_team=same_team,
        against=against,
        left_wins_against=left_wins_against,
        right_wins_against=right_wins_against,
    )
