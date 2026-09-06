"""Paris en monnaie virtuelle, a cotes fixes.

Aucun argent reel n'intervient et rien ne permet d'en ajouter : les pieces
sont des lignes dans un fichier SQLite local.

Modele de bookmaker plutot que parimutuel :

* la cote d'un camp suit l'argent mise dessus - plus il est charge, moins il
  paie - via une probabilite implicite lissee par une mise virtuelle ;
* la cote est **figee au moment du pari**. Celle affichee plus tard, apres que
  d'autres ont mise, ne change pas ce qui te sera paye ;
* la banque est la contrepartie : elle paie les gagnants et encaisse les
  perdants. Il y a donc toujours un gain ou une perte, jamais un remboursement.

Le parimutuel precedent avait un defaut fatal a six joueurs : quand tout le
monde misait du meme cote, la cagnotte ne contenait que les mises des gagnants
et leur etait rendue telle quelle - et sans personne du bon cote, tout etait
rembourse. Parier ne coutait ni ne rapportait rien.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import Bet, BetSide, GameStatus, TrackedGame, Wallet
from ..utils import as_utc, utcnow


def _side_label(side: str) -> str:
    return {"WIN": "VICTOIRE", "LOSS": "DÉFAITE"}.get(side, side)


class BettingError(Exception):
    """Erreur de l'utilisateur, formulée pour être affichée telle quelle."""


class BetsClosed(BettingError):
    pass


class InsufficientFunds(BettingError):
    pass


class DuplicateBet(BettingError):
    pass


class BetNotFound(BettingError):
    pass


class InvalidAmount(BettingError):
    pass


@dataclass(frozen=True, slots=True)
class Pool:
    win_amount: int = 0
    loss_amount: int = 0
    win_count: int = 0
    loss_count: int = 0
    # Cotes proposees en cet instant. Un pari place maintenant les fige.
    win_odds: float = 0.0
    loss_odds: float = 0.0

    @property
    def total(self) -> int:
        return self.win_amount + self.loss_amount

    @property
    def count(self) -> int:
        return self.win_count + self.loss_count

    def multiplier(self, side: str) -> float | None:
        """Cote actuelle du camp : ce que rapporterait une mise placee la."""
        odds = self.win_odds if side == BetSide.WIN else self.loss_odds
        return odds if odds > 0 else None

    def implied_probability(self, side: str) -> float | None:
        """Share of the pool on this side. This is what bettors believe,
        not a model prediction."""
        if self.total <= 0:
            return None
        side_amount = self.win_amount if side == BetSide.WIN else self.loss_amount
        return side_amount / self.total


def compute_odds(
    side_amount: int,
    total_amount: int,
    *,
    seed: int,
    margin: float,
    minimum: float,
    maximum: float,
) -> float:
    """Cote d'un camp d'apres l'argent deja mise.

    La mise virtuelle ``seed`` sert d'a priori : elle donne une cote
    d'ouverture symetrique quand personne n'a encore parie, et empeche une
    cote absurde des le premier pari. Plus un camp est charge, plus sa
    probabilite implicite monte, donc moins il paie.
    """
    probability = (side_amount + seed) / (total_amount + 2 * seed)
    fair = 1.0 / probability
    return round(max(minimum, min(maximum, fair * (1.0 - margin))), 2)


@dataclass(slots=True)
class Settlement:
    winning_side: str | None
    pool: Pool
    paid: list[tuple[int, int, int]]  # (user_id, stake, payout)
    lost: list[tuple[int, int]]  # (user_id, stake)
    refunded: bool = False

    @property
    def total_paid(self) -> int:
        return sum(payout for _, _, payout in self.paid)


class BettingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- wallets ----------------------------------------------------------

    async def get_wallet(
        self, session: AsyncSession, guild_id: int, user_id: int, *, create: bool = True
    ) -> Wallet:
        result = await session.execute(
            select(Wallet).where(Wallet.guild_id == guild_id, Wallet.user_id == user_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet is None and create:
            wallet = Wallet(
                guild_id=guild_id,
                user_id=user_id,
                balance=self._settings.starting_balance,
            )
            session.add(wallet)
            try:
                await session.flush()
            except IntegrityError:
                # Two commands raced to create the same wallet; take the winner.
                await session.rollback()
                result = await session.execute(
                    select(Wallet).where(Wallet.guild_id == guild_id, Wallet.user_id == user_id)
                )
                wallet = result.scalar_one()
        if wallet is None:  # create=False and nothing stored yet
            wallet = Wallet(
                guild_id=guild_id, user_id=user_id, balance=self._settings.starting_balance
            )
        return wallet

    async def claim_daily(
        self, session: AsyncSession, guild_id: int, user_id: int
    ) -> tuple[int, timedelta | None]:
        """Return (amount granted, time left) - amount is 0 when on cooldown."""
        wallet = await self.get_wallet(session, guild_id, user_id)
        now = utcnow()
        cooldown = timedelta(hours=self._settings.daily_cooldown_hours)
        last = as_utc(wallet.last_daily_at)
        if last is not None and now - last < cooldown:
            return 0, cooldown - (now - last)
        wallet.balance += self._settings.daily_amount
        wallet.last_daily_at = now
        session.add(wallet)
        return self._settings.daily_amount, None

    # -- pools ------------------------------------------------------------

    async def pool(self, session: AsyncSession, game_id: int) -> Pool:
        rows = (
            await session.execute(
                select(Bet.side, func.sum(Bet.amount), func.count(Bet.id))
                .where(Bet.game_id == game_id)
                .group_by(Bet.side)
            )
        ).all()
        totals = {side: (int(amount or 0), int(count or 0)) for side, amount, count in rows}
        win_amount, win_count = totals.get(BetSide.WIN, (0, 0))
        loss_amount, loss_count = totals.get(BetSide.LOSS, (0, 0))
        return self._with_odds(
            Pool(
                win_amount=win_amount,
                loss_amount=loss_amount,
                win_count=win_count,
                loss_count=loss_count,
            )
        )

    def _with_odds(self, pool: Pool) -> Pool:
        """Renseigne les cotes proposees pour cette repartition."""
        settings = self._settings
        options = {
            "seed": settings.odds_seed_coins,
            "margin": settings.odds_margin,
            "minimum": settings.odds_min,
            "maximum": settings.odds_max,
        }
        return Pool(
            win_amount=pool.win_amount,
            loss_amount=pool.loss_amount,
            win_count=pool.win_count,
            loss_count=pool.loss_count,
            win_odds=compute_odds(pool.win_amount, pool.total, **options),
            loss_odds=compute_odds(pool.loss_amount, pool.total, **options),
        )

    async def odds_for(self, session: AsyncSession, game_id: int, side: str) -> float:
        """Cote qu'un pari place maintenant figerait."""
        pool = await self.pool(session, game_id)
        return pool.multiplier(side) or self._settings.odds_min

    async def bets_for_game(self, session: AsyncSession, game_id: int) -> list[Bet]:
        result = await session.execute(
            select(Bet).where(Bet.game_id == game_id).order_by(Bet.amount.desc())
        )
        return list(result.scalars().all())

    async def get_bet(
        self, session: AsyncSession, game_id: int, user_id: int
    ) -> Bet | None:
        result = await session.execute(
            select(Bet).where(Bet.game_id == game_id, Bet.user_id == user_id)
        )
        return result.scalar_one_or_none()

    # -- placing / cancelling ---------------------------------------------

    @staticmethod
    def is_open(game: TrackedGame, *, now=None) -> bool:
        if game.status != GameStatus.LIVE:
            return False
        lock_at = as_utc(game.lock_at)
        return lock_at is None or (now or utcnow()) < lock_at

    async def place_bet(
        self,
        session: AsyncSession,
        game: TrackedGame,
        user_id: int,
        side: str,
        amount: int,
    ) -> tuple[Bet, Wallet]:
        if not self.is_open(game):
            raise BetsClosed("Les paris sont fermés pour cette partie.")
        if side not in (BetSide.WIN, BetSide.LOSS):
            raise InvalidAmount("Choisis VICTOIRE ou DÉFAITE.")
        if amount < self._settings.min_bet:
            raise InvalidAmount(f"Le pari minimum est de {self._settings.min_bet} pièces.")
        if amount > self._settings.max_bet:
            raise InvalidAmount(f"Le pari maximum est de {self._settings.max_bet:,} pièces.")

        existing = await self.get_bet(session, int(game.id or 0), user_id)
        if existing is not None:
            raise DuplicateBet(
                f"Tu as déjà {existing.amount:,} pièces sur "
                f"**{_side_label(existing.side)}**. Utilise `/annulerpari` "
                "si tu veux changer."
            )

        # La cote est lue AVANT d'ajouter la mise : parier ne doit pas
        # deplacer sa propre cote.
        odds = await self.odds_for(session, int(game.id or 0), side)

        wallet = await self.get_wallet(session, game.guild_id, user_id)
        if wallet.balance < amount:
            raise InsufficientFunds(
                f"Tu n'as que {wallet.balance:,} pièces. "
                "Essaie `/quotidien` pour te renflouer."
            )

        # Stake leaves the wallet now, so balances can never go negative and
        # the pool total always matches coins actually held in escrow.
        wallet.balance -= amount
        wallet.total_wagered += amount
        bet = Bet(
            game_id=int(game.id or 0),
            guild_id=game.guild_id,
            user_id=user_id,
            side=side,
            amount=amount,
            odds=odds,
        )
        session.add(wallet)
        session.add(bet)
        try:
            await session.flush()
        except IntegrityError as exc:
            # The UNIQUE (user_id, game_id) constraint caught a double click.
            await session.rollback()
            raise DuplicateBet("Tu as déjà un pari sur cette partie.") from exc
        return bet, wallet

    async def cancel_bet(
        self, session: AsyncSession, game: TrackedGame, user_id: int
    ) -> tuple[Bet, Wallet]:
        if not self.is_open(game):
            raise BetsClosed("Les paris sont verrouillés, celui-là part avec toi.")
        bet = await self.get_bet(session, int(game.id or 0), user_id)
        if bet is None:
            raise BetNotFound("Tu n'as aucun pari sur cette partie.")
        wallet = await self.get_wallet(session, game.guild_id, user_id)
        wallet.balance += bet.amount
        wallet.total_wagered = max(0, wallet.total_wagered - bet.amount)
        session.add(wallet)
        await session.delete(bet)
        await session.flush()
        return bet, wallet

    # -- settlement -------------------------------------------------------

    async def settle(
        self, session: AsyncSession, game: TrackedGame, tracked_team_won: bool
    ) -> Settlement:
        """Pay out a finished game. Idempotent per bet via ``settled_at``."""
        bets = (
            (await session.execute(select(Bet).where(Bet.game_id == game.id))).scalars().all()
        )
        pool = await self.pool(session, int(game.id or 0))
        winning_side = BetSide.WIN if tracked_team_won else BetSide.LOSS
        winners = [b for b in bets if b.side == winning_side and b.settled_at is None]
        losers = [b for b in bets if b.side != winning_side and b.settled_at is None]
        now = utcnow()

        paid: list[tuple[int, int, int]] = []
        for bet in winners:
            # Chacun est paye a SA cote, celle figee quand il a mise.
            odds = bet.odds if bet.odds > 1 else self._settings.odds_min
            payout = int(bet.amount * odds)
            wallet = await self.get_wallet(session, game.guild_id, bet.user_id)
            wallet.balance += payout
            wallet.bets_won += 1
            wallet.net_profit += payout - bet.amount
            bet.payout = payout
            bet.settled_at = now
            session.add(wallet)
            session.add(bet)
            paid.append((bet.user_id, bet.amount, payout))

        lost: list[tuple[int, int]] = []
        for bet in losers:
            wallet = await self.get_wallet(session, game.guild_id, bet.user_id)
            wallet.bets_lost += 1
            wallet.net_profit -= bet.amount
            bet.payout = 0
            bet.settled_at = now
            session.add(wallet)
            session.add(bet)
            lost.append((bet.user_id, bet.amount))

        await session.flush()
        return Settlement(winning_side=winning_side, pool=pool, paid=paid, lost=lost)

    async def refund_all(self, session: AsyncSession, game: TrackedGame) -> Settlement:
        bets = (
            (await session.execute(select(Bet).where(Bet.game_id == game.id))).scalars().all()
        )
        return await self._refund(session, bets, reason_void=True)

    async def _refund(
        self, session: AsyncSession, bets: list[Bet], *, reason_void: bool
    ) -> Settlement:
        now = utcnow()
        refunded: list[tuple[int, int, int]] = []
        pool = Pool(
            win_amount=sum(b.amount for b in bets if b.side == BetSide.WIN),
            loss_amount=sum(b.amount for b in bets if b.side == BetSide.LOSS),
            win_count=sum(1 for b in bets if b.side == BetSide.WIN),
            loss_count=sum(1 for b in bets if b.side == BetSide.LOSS),
        )
        for bet in bets:
            if bet.settled_at is not None:
                continue
            wallet = await self.get_wallet(session, bet.guild_id, bet.user_id)
            wallet.balance += bet.amount
            wallet.total_wagered = max(0, wallet.total_wagered - bet.amount)
            bet.payout = bet.amount
            bet.settled_at = now
            session.add(wallet)
            session.add(bet)
            refunded.append((bet.user_id, bet.amount, bet.amount))
        await session.flush()
        return Settlement(winning_side=None, pool=pool, paid=refunded, lost=[], refunded=True)

    # -- leaderboard ------------------------------------------------------

    async def leaderboard(
        self, session: AsyncSession, guild_id: int, limit: int = 10
    ) -> list[Wallet]:
        result = await session.execute(
            select(Wallet)
            .where(Wallet.guild_id == guild_id)
            .order_by(Wallet.balance.desc(), Wallet.net_profit.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
