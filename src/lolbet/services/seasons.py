"""Saisons de paris et palmarès.

Une saison est ouverte automatiquement à la première utilisation. La clôturer
fige le classement dans une table d'archive, puis remet tous les soldes à leur
valeur de départ : sans remise à zéro, celui qui a pris de l'avance la garde
indéfiniment et le classement n'intéresse plus personne.

Les soldes sont réinitialisés, jamais l'historique des parties : /historique
continue de tout montrer.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Player, Season, SeasonStanding, Wallet
from ..utils import utcnow


class SeasonError(Exception):
    """Message destiné à être affiché tel quel."""


@dataclass(frozen=True, slots=True)
class ClosedSeason:
    season: Season
    standings: list[SeasonStanding]

    @property
    def champion(self) -> SeasonStanding | None:
        return self.standings[0] if self.standings else None


async def current_season(session: AsyncSession, guild_id: int) -> Season | None:
    result = await session.execute(
        select(Season)
        .where(Season.guild_id == guild_id, Season.ended_at.is_(None))
        .order_by(Season.number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def ensure_season(
    session: AsyncSession, guild_id: int, *, starting_balance: int
) -> Season:
    """Renvoie la saison en cours, en la créant au besoin."""
    season = await current_season(session, guild_id)
    if season is not None:
        return season

    last = (
        await session.execute(
            select(Season)
            .where(Season.guild_id == guild_id)
            .order_by(Season.number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    number = (last.number + 1) if last else 1

    season = Season(
        guild_id=guild_id,
        number=number,
        name=f"Saison {number}",
        starting_balance=starting_balance,
    )
    session.add(season)
    await session.flush()
    return season


async def close_season(
    session: AsyncSession, guild_id: int, *, starting_balance: int, reset: bool = True
) -> ClosedSeason:
    """Fige le classement, puis remet les soldes à zéro et ouvre la suivante."""
    season = await current_season(session, guild_id)
    if season is None:
        raise SeasonError("Aucune saison en cours sur ce serveur.")

    wallets = (
        (
            await session.execute(
                select(Wallet)
                .where(Wallet.guild_id == guild_id)
                .order_by(Wallet.balance.desc(), Wallet.net_profit.desc())
            )
        )
        .scalars()
        .all()
    )
    if not wallets:
        raise SeasonError("Personne n'a encore parié : rien à archiver.")

    riot_ids = {
        player.discord_id: player.riot_id
        for player in (
            await session.execute(select(Player).where(Player.guild_id == guild_id))
        )
        .scalars()
        .all()
    }

    standings: list[SeasonStanding] = []
    for position, wallet in enumerate(wallets, start=1):
        standing = SeasonStanding(
            season_id=int(season.id or 0),
            guild_id=guild_id,
            user_id=wallet.user_id,
            position=position,
            balance=wallet.balance,
            bets_won=wallet.bets_won,
            bets_lost=wallet.bets_lost,
            net_profit=wallet.net_profit,
            total_wagered=wallet.total_wagered,
            riot_id=riot_ids.get(wallet.user_id, ""),
        )
        session.add(standing)
        standings.append(standing)

        if reset:
            wallet.balance = starting_balance
            wallet.bets_won = 0
            wallet.bets_lost = 0
            wallet.net_profit = 0
            wallet.total_wagered = 0
            session.add(wallet)

    season.ended_at = utcnow()
    session.add(season)
    await session.flush()

    # La suivante s'ouvre tout de suite : les paris ne doivent jamais être
    # bloqués parce qu'une saison vient de se terminer.
    await ensure_season(session, guild_id, starting_balance=starting_balance)
    return ClosedSeason(season=season, standings=standings)


async def past_seasons(session: AsyncSession, guild_id: int, limit: int = 10) -> list[Season]:
    result = await session.execute(
        select(Season)
        .where(Season.guild_id == guild_id, Season.ended_at.is_not(None))
        .order_by(Season.number.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def standings_of(
    session: AsyncSession, season_id: int, limit: int = 10
) -> list[SeasonStanding]:
    result = await session.execute(
        select(SeasonStanding)
        .where(SeasonStanding.season_id == season_id)
        .order_by(SeasonStanding.position)
        .limit(limit)
    )
    return list(result.scalars().all())


async def hall_of_fame(session: AsyncSession, guild_id: int) -> list[tuple[int, int]]:
    """(user_id, titres) : qui a gagné le plus de saisons."""
    rows = (
        (
            await session.execute(
                select(SeasonStanding.user_id).where(
                    SeasonStanding.guild_id == guild_id, SeasonStanding.position == 1
                )
            )
        )
        .scalars()
        .all()
    )
    counts: dict[int, int] = {}
    for user_id in rows:
        counts[user_id] = counts.get(user_id, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
