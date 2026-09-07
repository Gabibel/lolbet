"""Relevés de rang Overwatch : lecture, écriture, et ce qui a changé.

Le pendant de ``progression.py`` pour Overwatch, avec une différence de fond :
il n'y a pas de points à additionner. On compare deux positions sur l'échelle
division/palier, et on dit de combien de crans ça a bougé — jamais « +18 »,
puisque le jeu ne publie pas ce chiffre.

Un relevé n'est écrit que si le rang a changé, sinon la table grossirait d'une
ligne identique à chaque passage de la boucle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import OverwatchPlayer, OverwatchRankSnapshot
from ..overwatch.rank import DIVISIONS, ROLES, OwRank, normalise_division
from ..utils import utcnow


def rank_of(snapshot: OverwatchRankSnapshot) -> OwRank:
    return OwRank(
        role=snapshot.role,
        division=normalise_division(snapshot.division),
        tier=snapshot.tier,
    )


@dataclass(frozen=True, slots=True)
class RoleChange:
    """Ce qui a bougé sur un rôle entre deux relevés."""

    role: str
    current: OwRank
    previous: OwRank | None

    @property
    def is_placement(self) -> bool:
        """Un rôle qui n'avait aucun rang et qui en a un maintenant."""
        return self.previous is None

    @property
    def steps(self) -> int:
        """Écart en crans. Un cran = un palier ; cinq crans = une division."""
        if self.previous is None:
            return 0
        return self.current.score - self.previous.score

    @property
    def direction(self) -> int:
        if self.steps > 0:
            return 1
        return -1 if self.steps < 0 else 0

    @property
    def changed_division(self) -> bool:
        if self.previous is None:
            return False
        return self.previous.division != self.current.division

    @property
    def category(self) -> str:
        """La situation à raconter, de la plus forte à la plus banale."""
        if self.is_placement:
            return "placed"
        if self.changed_division:
            return "promoted" if self.direction > 0 else "demoted"
        return "tier_up" if self.direction > 0 else "tier_down"

    @property
    def arrow(self) -> str:
        if self.direction > 0:
            return "\N{UPWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}"
        if self.direction < 0:
            return "\N{DOWNWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}"
        return "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}"

    @property
    def line(self) -> str:
        """``DPS — 🟡 Or 3 ⬆️ 🟡 Or 2``, ou le rang seul pour un placement."""
        if self.previous is None:
            return f"{self.current.display} \N{BULLET} nouveau"
        return (
            f"{self.current.role_label} \N{EM DASH} "
            f"{self.previous.label} {self.arrow} {self.current.label}"
        )


# -- joueurs ---------------------------------------------------------------


async def linked_ow_players(
    session: AsyncSession, guild_id: int | None = None
) -> list[OverwatchPlayer]:
    statement = select(OverwatchPlayer)
    if guild_id is not None:
        statement = statement.where(OverwatchPlayer.guild_id == guild_id)
    rows = (await session.execute(statement.order_by(OverwatchPlayer.battletag))).scalars()
    return list(rows)


async def ow_player_for(
    session: AsyncSession, guild_id: int, discord_id: int
) -> OverwatchPlayer | None:
    return (
        await session.execute(
            select(OverwatchPlayer).where(
                OverwatchPlayer.guild_id == guild_id,
                OverwatchPlayer.discord_id == discord_id,
            )
        )
    ).scalar_one_or_none()


# -- relevés ---------------------------------------------------------------


async def latest_ow_snapshot(
    session: AsyncSession, battletag: str, role: str, platform: str = "pc"
) -> OverwatchRankSnapshot | None:
    statement = (
        select(OverwatchRankSnapshot)
        .where(
            OverwatchRankSnapshot.battletag == battletag,
            OverwatchRankSnapshot.role == role,
            OverwatchRankSnapshot.platform == platform,
        )
        .order_by(
            OverwatchRankSnapshot.captured_at.desc(), OverwatchRankSnapshot.id.desc()
        )
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def latest_ow_ranks(
    session: AsyncSession, battletag: str, platform: str = "pc"
) -> dict[str, OwRank]:
    """Le dernier rang connu de chaque rôle."""
    ranks: dict[str, OwRank] = {}
    for role in ROLES:
        snapshot = await latest_ow_snapshot(session, battletag, role, platform)
        if snapshot is not None:
            ranks[role] = rank_of(snapshot)
    return ranks


async def has_any_snapshot(
    session: AsyncSession, battletag: str, platform: str = "pc"
) -> bool:
    """Vrai si le bot a déjà relevé ce compte au moins une fois."""
    found = (
        await session.execute(
            select(OverwatchRankSnapshot.id)
            .where(
                OverwatchRankSnapshot.battletag == battletag,
                OverwatchRankSnapshot.platform == platform,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def record_ow_snapshot(
    session: AsyncSession,
    *,
    battletag: str,
    platform: str,
    rank: OwRank,
    season: int | None = None,
) -> OverwatchRankSnapshot | None:
    """Écrit un relevé si le rang a changé. Renvoie le relevé, ou None."""
    previous = await latest_ow_snapshot(session, battletag, rank.role, platform)
    if (
        previous is not None
        and normalise_division(previous.division) == rank.division
        and previous.tier == rank.tier
    ):
        return None

    snapshot = OverwatchRankSnapshot(
        battletag=battletag,
        platform=platform,
        role=rank.role,
        division=rank.division,
        tier=rank.tier,
        ladder_score=rank.score,
        season=season,
        captured_at=utcnow(),
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def apply_ranks(
    session: AsyncSession,
    *,
    battletag: str,
    platform: str,
    ranks: dict[str, OwRank],
    season: int | None = None,
) -> list[RoleChange]:
    """Enregistre ce qui a bougé et renvoie les changements à annoncer.

    Le tout premier passage sur un compte ne renvoie rien : à ce moment le
    bot découvre le rang, il ne le voit pas monter. Annoncer une promotion
    là serait faux.
    """
    baseline = not await has_any_snapshot(session, battletag, platform)

    changes: list[RoleChange] = []
    for role in ROLES:
        rank = ranks.get(role)
        if rank is None:
            continue
        previous_row = await latest_ow_snapshot(session, battletag, role, platform)
        previous = rank_of(previous_row) if previous_row is not None else None
        stored = await record_ow_snapshot(
            session, battletag=battletag, platform=platform, rank=rank, season=season
        )
        if stored is None or baseline:
            continue
        changes.append(RoleChange(role=role, current=rank, previous=previous))
    return changes


async def ow_history(
    session: AsyncSession,
    battletag: str,
    *,
    role: str | None = None,
    platform: str = "pc",
    days: int = 90,
) -> list[OverwatchRankSnapshot]:
    since = utcnow() - timedelta(days=days)
    statement = select(OverwatchRankSnapshot).where(
        OverwatchRankSnapshot.battletag == battletag,
        OverwatchRankSnapshot.platform == platform,
        OverwatchRankSnapshot.captured_at >= since,
    )
    if role:
        statement = statement.where(OverwatchRankSnapshot.role == role)
    rows = (
        await session.execute(statement.order_by(OverwatchRankSnapshot.captured_at.asc()))
    ).scalars()
    return list(rows)


async def peak_rank(
    session: AsyncSession, battletag: str, role: str, platform: str = "pc"
) -> OverwatchRankSnapshot | None:
    """Le meilleur rang jamais relevé sur ce rôle."""
    statement = (
        select(OverwatchRankSnapshot)
        .where(
            OverwatchRankSnapshot.battletag == battletag,
            OverwatchRankSnapshot.role == role,
            OverwatchRankSnapshot.platform == platform,
        )
        .order_by(
            OverwatchRankSnapshot.ladder_score.desc(),
            OverwatchRankSnapshot.captured_at.asc(),
        )
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


def division_gap(first: OwRank, second: OwRank) -> int:
    """Nombre de divisions entre deux rangs, signé."""
    if not (first.known and second.known):
        return 0
    return DIVISIONS.index(second.division) - DIVISIONS.index(first.division)
