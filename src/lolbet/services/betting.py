"""Virtual-currency parimutuel betting.

There is no real money anywhere in this bot and no path to add any. Coins are
rows in a local SQLite file.

Pool rules:
  payout = stake * (total_pool / winning_side_pool), 0% rake.
Payouts are integers, and the rounding remainder is handed out largest-
remainder style so the pool is conserved to the coin instead of quietly
evaporating.
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


class BettingError(Exception):
    """Anything the user did wrong, phrased so it can be shown as-is."""


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

    @property
    def total(self) -> int:
        return self.win_amount + self.loss_amount

    @property
    def count(self) -> int:
        return self.win_count + self.loss_count

    def multiplier(self, side: str) -> float | None:
        """What one coin on ``side`` pays if that side wins."""
        side_amount = self.win_amount if side == BetSide.WIN else self.loss_amount
        if side_amount <= 0 or self.total <= 0:
            return None
        return self.total / side_amount

    def implied_probability(self, side: str) -> float | None:
        """Share of the pool on this side. This is what bettors believe,
        not a model prediction."""
        if self.total <= 0:
            return None
        side_amount = self.win_amount if side == BetSide.WIN else self.loss_amount
        return side_amount / self.total


def compute_payouts(stakes: dict[int, int], winning_total: int, pool_total: int) -> dict[int, int]:
    """Split ``pool_total`` across winning stakes, conserving every coin.

    ``stakes`` maps bet id -> stake for the winning side only.
    """
    if not stakes or winning_total <= 0:
        return {}
    exact = {bet_id: stake * pool_total / winning_total for bet_id, stake in stakes.items()}
    payouts = {bet_id: int(value) for bet_id, value in exact.items()}
    remainder = pool_total - sum(payouts.values())
    if remainder > 0:
        # Largest fractional part first; ties broken by the bigger stake.
        order = sorted(
            exact,
            key=lambda bet_id: (exact[bet_id] - payouts[bet_id], stakes[bet_id]),
            reverse=True,
        )
        for bet_id in order[:remainder]:
            payouts[bet_id] += 1
    return payouts


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
        return Pool(
            win_amount=win_amount,
            loss_amount=loss_amount,
            win_count=win_count,
            loss_count=loss_count,
        )

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
            raise BetsClosed("Betting is closed for this game.")
        if side not in (BetSide.WIN, BetSide.LOSS):
            raise InvalidAmount("Pick either WIN or LOSS.")
        if amount < self._settings.min_bet:
            raise InvalidAmount(f"Minimum bet is {self._settings.min_bet} coins.")
        if amount > self._settings.max_bet:
            raise InvalidAmount(f"Maximum bet is {self._settings.max_bet:,} coins.")

        existing = await self.get_bet(session, int(game.id or 0), user_id)
        if existing is not None:
            raise DuplicateBet(
                f"You already have {existing.amount:,} coins on **{existing.side}**. "
                "Use `/cancelbet` first if you want to change it."
            )

        wallet = await self.get_wallet(session, game.guild_id, user_id)
        if wallet.balance < amount:
            raise InsufficientFunds(
                f"You only have {wallet.balance:,} coins. Try `/daily` for a top-up."
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
        )
        session.add(wallet)
        session.add(bet)
        try:
            await session.flush()
        except IntegrityError as exc:
            # The UNIQUE (user_id, game_id) constraint caught a double click.
            await session.rollback()
            raise DuplicateBet("You already have a bet on this game.") from exc
        return bet, wallet

    async def cancel_bet(
        self, session: AsyncSession, game: TrackedGame, user_id: int
    ) -> tuple[Bet, Wallet]:
        if not self.is_open(game):
            raise BetsClosed("Bets are locked; this one has to ride.")
        bet = await self.get_bet(session, int(game.id or 0), user_id)
        if bet is None:
            raise BetNotFound("You have no bet on this game.")
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

        if not winners:
            # Nobody backed the winning side: refund everyone rather than
            # burning the pool.
            return await self._refund(session, bets, reason_void=False)

        winning_total = sum(b.amount for b in winners)
        stakes = {int(b.id or 0): b.amount for b in winners}
        payouts = compute_payouts(stakes, winning_total, pool.total)

        paid: list[tuple[int, int, int]] = []
        for bet in winners:
            payout = payouts.get(int(bet.id or 0), bet.amount)
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
