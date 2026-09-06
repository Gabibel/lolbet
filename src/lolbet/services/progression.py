"""Relevés de rang et progression de LP.

Un relevé est enregistré après chaque partie réglée, en forçant une lecture
fraîche de LEAGUE-V4 : la valeur en cache a six heures et ne refléterait pas
le gain ou la perte de la partie qui vient de se terminer.

Un relevé n'est écrit que si le rang a bougé, sinon la table grossirait d'une
ligne identique par partie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_conf import get_logger
from ..models import RankSnapshot
from ..riot.client import RiotAPIError, RiotClient
from ..riot.rank import RankInfo, solo_queue_rank
from ..utils import as_utc, utcnow

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Progression:
    """Évolution entre le premier et le dernier relevé d'une période."""

    first: RankSnapshot | None
    last: RankSnapshot | None
    snapshots: list[RankSnapshot]

    @property
    def has_data(self) -> bool:
        return self.last is not None

    @property
    def delta(self) -> int:
        """Écart en points d'échelle : comparable entre paliers."""
        if self.first is None or self.last is None:
            return 0
        return self.last.ladder_score - self.first.ladder_score

    @property
    def games(self) -> int:
        return sum(1 for s in self.snapshots if s.game_id is not None)


@dataclass(frozen=True, slots=True)
class RankChange:
    """Ce qu'une partie a coûté ou rapporté en LP."""

    puuid: str
    previous: RankSnapshot | None
    current: RankSnapshot

    @property
    def known(self) -> bool:
        """Faux au tout premier relevé : il n'y a rien à comparer."""
        return self.previous is not None

    @property
    def delta(self) -> int:
        if self.previous is None:
            return 0
        return self.current.ladder_score - self.previous.ladder_score

    @property
    def direction(self) -> int:
        """+1 promu, -1 rétrogradé, 0 même division."""
        if self.previous is None:
            return 0
        before = (self.previous.tier, self.previous.division)
        after = (self.current.tier, self.current.division)
        if before == after:
            return 0
        return 1 if self.current.ladder_score > self.previous.ladder_score else -1

    @property
    def label(self) -> str:
        return snapshot_label(self.current)

    @property
    def signed_delta(self) -> str:
        return f"{self.delta:+d} LP" if self.known else "LP inconnus"


def _to_info(snapshot: RankSnapshot) -> RankInfo:
    return RankInfo(
        queue=snapshot.queue,
        tier=snapshot.tier,
        division=snapshot.division,
        league_points=snapshot.league_points,
        wins=snapshot.wins,
        losses=snapshot.losses,
    )


def snapshot_label(snapshot: RankSnapshot) -> str:
    return _to_info(snapshot).display


async def latest_snapshot(
    session: AsyncSession, puuid: str, queue: str | None = None
) -> RankSnapshot | None:
    statement = select(RankSnapshot).where(RankSnapshot.puuid == puuid)
    if queue:
        statement = statement.where(RankSnapshot.queue == queue)
    statement = statement.order_by(
        RankSnapshot.captured_at.desc(), RankSnapshot.id.desc()
    ).limit(1)
    return (await session.execute(statement)).scalar_one_or_none()


async def record_snapshot(
    session: AsyncSession,
    *,
    puuid: str,
    platform: str,
    rank: RankInfo,
    game_id: int | None = None,
) -> RankSnapshot | None:
    """Écrit un relevé si le rang a changé. Renvoie le relevé, ou None."""
    previous = await latest_snapshot(session, puuid, rank.queue)
    if (
        previous is not None
        and previous.tier == rank.tier.upper()
        and previous.division == rank.division.upper()
        and previous.league_points == rank.league_points
    ):
        return None

    snapshot = RankSnapshot(
        puuid=puuid,
        platform=platform,
        queue=rank.queue,
        tier=rank.tier.upper(),
        division=rank.division.upper(),
        league_points=rank.league_points,
        ladder_score=rank.score,
        wins=rank.wins,
        losses=rank.losses,
        game_id=game_id,
        captured_at=utcnow(),
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def capture_after_game(
    session: AsyncSession,
    riot: RiotClient,
    *,
    puuid: str,
    platform: str,
    game_id: int | None = None,
) -> RankChange | None:
    """Relit le rang hors cache et renvoie ce que la partie a changé.

    Le relevé précédent est lu **avant** l'écriture du nouveau, sinon l'écart
    serait toujours nul.
    """
    try:
        entries = await riot.refresh_league_entries(puuid, platform)
    except RiotAPIError as exc:
        log.warning("progression.fetch_failed", puuid=puuid[:8], error=str(exc))
        return None

    rank = solo_queue_rank(entries)
    if rank is None:
        return None

    previous = await latest_snapshot(session, puuid, rank.queue)
    stored = await record_snapshot(
        session, puuid=puuid, platform=platform, rank=rank, game_id=game_id
    )
    # stored vaut None quand le rang n'a pas bougé : le relevé courant est
    # alors le précédent, et l'écart est nul.
    current = stored or previous
    if current is None:
        return None
    return RankChange(
        puuid=puuid,
        previous=previous if stored is not None else previous,
        current=current,
    )


async def progression(
    session: AsyncSession, puuid: str, *, days: int = 30, queue: str | None = None
) -> Progression:
    since = utcnow() - timedelta(days=days)
    statement = select(RankSnapshot).where(
        RankSnapshot.puuid == puuid, RankSnapshot.captured_at >= since
    )
    if queue:
        statement = statement.where(RankSnapshot.queue == queue)
    rows = (
        (await session.execute(statement.order_by(RankSnapshot.captured_at.asc())))
        .scalars()
        .all()
    )
    snapshots = list(rows)
    if not snapshots:
        # Aucun relevé dans la fenêtre : au moins montrer le rang actuel.
        last = await latest_snapshot(session, puuid, queue)
        return Progression(first=None, last=last, snapshots=[last] if last else [])
    return Progression(first=snapshots[0], last=snapshots[-1], snapshots=snapshots)


def sparkline(snapshots: list[RankSnapshot], width: int = 12) -> str:
    """Petit graphe en blocs des derniers relevés."""
    blocks = "▁▂▃▄▅▆▇█"
    values = [s.ladder_score for s in snapshots][-width:]
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    if high == low:
        return blocks[0] * len(values)
    span = high - low
    return "".join(blocks[min(7, int((v - low) / span * 7))] for v in values)


def days_since(snapshot: RankSnapshot | None) -> int | None:
    if snapshot is None:
        return None
    captured = as_utc(snapshot.captured_at)
    if captured is None:
        return None
    return max(0, (utcnow() - captured).days)
