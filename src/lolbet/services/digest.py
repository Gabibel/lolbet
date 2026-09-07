"""Le bilan de la semaine, agrégé depuis ce qui est déjà en base.

Le bot ne parlait que quand quelqu'un jouait. Ce module lui donne un
rendez-vous : une fois par semaine, il raconte ce qui s'est passé même si la
semaine a été calme.

Aucun appel à Riot ici. Tout sort de ``player_game_stat``, ``rank_snapshot``
et ``bet``, qui sont figés au moment du règlement — le bilan d'une semaine
passée ne peut donc pas changer entre deux affichages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Bet, PlayerGameStat
from ..utils import as_utc, utcnow
from .progression import lp_delta

DEFAULT_DAYS = 7


def timezone_or_utc(name: str):
    """Le fuseau demandé, ou UTC. Un fuseau invalide ne doit rien casser.

    Le bilan tombera à la mauvaise heure, ce qui se voit et se corrige ;
    une exception au démarrage arrêterait le bot entier.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


@dataclass(frozen=True, slots=True)
class PlayerWeek:
    """Ce qu'un joueur a fait sur la période."""

    discord_id: int
    puuid: str
    games: int
    wins: int
    losses: int
    kills: int
    deaths: int
    assists: int
    mvp: int
    lvp: int
    # None quand aucun relevé ne permet de mesurer l'écart : on ne comble
    # pas le trou avec un zéro.
    lp: int | None = None

    @property
    def winrate(self) -> float | None:
        return (self.wins / self.games * 100) if self.games else None

    @property
    def kda(self) -> float:
        return (self.kills + self.assists) / max(1, self.deaths)


@dataclass(frozen=True, slots=True)
class BettorWeek:
    user_id: int
    settled: int
    won: int
    profit: int


@dataclass(frozen=True, slots=True)
class WeeklyDigest:
    since: datetime
    until: datetime
    players: list[PlayerWeek] = field(default_factory=list)
    bettors: list[BettorWeek] = field(default_factory=list)
    best_game: PlayerGameStat | None = None
    worst_game: PlayerGameStat | None = None
    longest_game: PlayerGameStat | None = None
    # Parties distinctes, pas lignes de statistiques : deux joueurs suivis
    # dans la même partie donnent deux lignes, les compter séparément
    # gonflerait le total.
    games: int = 0

    @property
    def has_data(self) -> bool:
        return bool(self.players)

    @property
    def total_deaths(self) -> int:
        return sum(p.deaths for p in self.players)

    @property
    def climber(self) -> PlayerWeek | None:
        """Celui qui a le plus progressé, s'il a progressé."""
        measured = [p for p in self.players if p.lp is not None and p.lp > 0]
        return max(measured, key=lambda p: p.lp or 0) if measured else None

    @property
    def faller(self) -> PlayerWeek | None:
        measured = [p for p in self.players if p.lp is not None and p.lp < 0]
        return min(measured, key=lambda p: p.lp or 0) if measured else None

    @property
    def feeder(self) -> PlayerWeek | None:
        """Le plus de morts sur la semaine, à condition d'avoir joué."""
        played = [p for p in self.players if p.games]
        return max(played, key=lambda p: p.deaths) if played else None


async def build_digest(
    session: AsyncSession, guild_id: int, *, days: int = DEFAULT_DAYS
) -> WeeklyDigest:
    """Agrège la période écoulée pour un serveur."""
    until = utcnow()
    since = until - timedelta(days=days)

    rows = (
        (
            await session.execute(
                select(PlayerGameStat).where(
                    PlayerGameStat.guild_id == guild_id,
                    PlayerGameStat.played_at >= since,
                )
            )
        )
        .scalars()
        .all()
    )
    stats = list(rows)

    by_player: dict[int, list[PlayerGameStat]] = {}
    for stat in stats:
        by_player.setdefault(stat.discord_id, []).append(stat)

    players: list[PlayerWeek] = []
    for discord_id, lines in by_player.items():
        puuid = lines[0].puuid
        players.append(
            PlayerWeek(
                discord_id=discord_id,
                puuid=puuid,
                games=len(lines),
                wins=sum(1 for line in lines if line.win),
                losses=sum(1 for line in lines if not line.win),
                kills=sum(line.kills for line in lines),
                deaths=sum(line.deaths for line in lines),
                assists=sum(line.assists for line in lines),
                mvp=sum(1 for line in lines if line.is_mvp),
                lvp=sum(1 for line in lines if line.is_lvp),
                lp=await lp_delta(session, puuid, since=since),
            )
        )
    players.sort(key=lambda p: (-p.games, -p.kda))

    bettors = await _bettors(session, guild_id, since)

    return WeeklyDigest(
        since=since,
        until=until,
        players=players,
        bettors=bettors,
        best_game=max(stats, key=lambda s: s.score) if stats else None,
        worst_game=min(stats, key=lambda s: s.score) if stats else None,
        longest_game=max(stats, key=lambda s: s.duration_seconds) if stats else None,
        games=len({stat.game_id for stat in stats}),
    )


async def _bettors(
    session: AsyncSession, guild_id: int, since: datetime
) -> list[BettorWeek]:
    rows = (
        (
            await session.execute(
                select(Bet).where(
                    Bet.guild_id == guild_id,
                    Bet.settled_at.is_not(None),
                    Bet.settled_at >= since,
                )
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[int, list[Bet]] = {}
    for bet in rows:
        grouped.setdefault(bet.user_id, []).append(bet)

    bettors = [
        BettorWeek(
            user_id=user_id,
            settled=len(bets),
            won=sum(1 for bet in bets if (bet.payout or 0) > bet.amount),
            profit=sum((bet.payout or 0) - bet.amount for bet in bets),
        )
        for user_id, bets in grouped.items()
    ]
    bettors.sort(key=lambda b: -b.profit)
    return bettors


def next_occurrence(
    now: datetime, weekday: int, hour: int, *, tzinfo=None
) -> datetime:
    """Prochaine occurrence du créneau hebdomadaire, à partir de ``now``.

    ``weekday`` suit ``datetime.weekday()`` : 0 = lundi, 6 = dimanche.
    """
    local = now.astimezone(tzinfo) if tzinfo is not None else now
    target = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    ahead = (weekday - target.weekday()) % 7
    target += timedelta(days=ahead)
    if target <= local:
        target += timedelta(days=7)
    return target


def is_due(
    now: datetime, last_sent: datetime | None, weekday: int, hour: int, *, tzinfo=None
) -> bool:
    """Vrai si le dernier créneau échu n'a pas encore été servi.

    ``last_sent`` à None veut dire « pas de repère » et non « jamais envoyé,
    donc rattrape tout » : sinon une installation neuve posterait un bilan
    dans la minute, à une heure quelconque. Le planificateur pose le repère
    au premier passage et le premier vrai bilan tombe au créneau suivant.

    On ne rattrape jamais plus d'un bilan : après trois semaines d'arrêt, le
    bot en poste un seul.
    """
    if last_sent is None:
        return False
    local = now.astimezone(tzinfo) if tzinfo is not None else now
    # Le dernier créneau échu, c'est la prochaine occurrence moins sept jours.
    previous = next_occurrence(local, weekday, hour, tzinfo=tzinfo) - timedelta(days=7)
    return as_utc(last_sent) < previous
