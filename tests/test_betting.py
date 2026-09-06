"""Parimutuel pool maths and the wallet lifecycle."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lolbet.models import BetSide, GameStatus, TrackedGame
from lolbet.services.betting import (
    BetsClosed,
    DuplicateBet,
    InsufficientFunds,
    InvalidAmount,
    Pool,
    compute_payouts,
)
from lolbet.utils import utcnow

GUILD = 1234
ALICE, BOB, CAROL = 11, 22, 33


async def make_game(session_factory, *, status: str = GameStatus.LIVE, lock_in: int = 300):
    async with session_factory() as session:
        game = TrackedGame(
            guild_id=GUILD,
            riot_game_id="EUW1_1",
            platform="euw1",
            queue_id=420,
            status=status,
            tracked_team_id=100,
            game_start_at=utcnow(),
            lock_at=utcnow() + timedelta(seconds=lock_in),
            channel_id=1,
            watcher_puuid="p1",
        )
        session.add(game)
        await session.commit()
        return game


# -- pure maths ------------------------------------------------------------


def test_payout_formula_is_stake_times_pool_over_winning_side():
    # 100 on the winning side, 300 in the pool -> x3.
    payouts = compute_payouts({1: 100}, winning_total=100, pool_total=300)
    assert payouts == {1: 300}


def test_payouts_split_proportionally():
    payouts = compute_payouts({1: 100, 2: 300}, winning_total=400, pool_total=800)
    assert payouts == {1: 200, 2: 600}


def test_rounding_remainder_is_distributed_not_burned():
    """Three winners on a pool that does not divide evenly must still add up."""
    payouts = compute_payouts({1: 1, 2: 1, 3: 1}, winning_total=3, pool_total=10)
    assert sum(payouts.values()) == 10
    assert sorted(payouts.values()) == [3, 3, 4]


def test_no_winners_means_no_payouts():
    assert compute_payouts({}, winning_total=0, pool_total=500) == {}


def test_pool_multipliers_and_implied_probability():
    pool = Pool(win_amount=300, loss_amount=100, win_count=2, loss_count=1)
    assert pool.total == 400
    assert pool.multiplier(BetSide.WIN) == pytest.approx(400 / 300)
    assert pool.multiplier(BetSide.LOSS) == pytest.approx(4.0)
    assert pool.implied_probability(BetSide.WIN) == pytest.approx(0.75)


def test_empty_pool_has_no_odds():
    pool = Pool()
    assert pool.multiplier(BetSide.WIN) is None
    assert pool.implied_probability(BetSide.WIN) is None


def test_zero_rake_conserves_the_pool():
    stakes = {1: 137, 2: 42, 3: 991}
    total = sum(stakes.values()) + 555  # losing side
    payouts = compute_payouts(stakes, sum(stakes.values()), total)
    assert sum(payouts.values()) == total


# -- placing bets ----------------------------------------------------------


async def test_place_bet_moves_coins_into_escrow(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        bet, wallet = await betting.place_bet(session, game, ALICE, BetSide.WIN, 250)
        await session.commit()

    assert bet.amount == 250
    assert wallet.balance == 750  # 1000 starting - 250 staked
    assert wallet.total_wagered == 250


async def test_one_position_per_user_per_game(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(DuplicateBet):
            await betting.place_bet(session, game, ALICE, BetSide.LOSS, 100)


async def test_balance_can_never_go_negative(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        with pytest.raises(InsufficientFunds):
            await betting.place_bet(session, game, ALICE, BetSide.WIN, 5000)


async def test_bet_amount_bounds_are_enforced(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        with pytest.raises(InvalidAmount):
            await betting.place_bet(session, game, ALICE, BetSide.WIN, 0)
        with pytest.raises(InvalidAmount):
            await betting.place_bet(session, game, ALICE, BetSide.WIN, 10**9)


async def test_bets_are_refused_once_locked(session_factory, betting):
    game = await make_game(session_factory, status=GameStatus.LOCKED)
    async with session_factory() as session:
        with pytest.raises(BetsClosed):
            await betting.place_bet(session, game, ALICE, BetSide.WIN, 10)


async def test_bets_are_refused_after_the_lock_time_passes(session_factory, betting):
    game = await make_game(session_factory, lock_in=-1)
    assert betting.is_open(game) is False
    async with session_factory() as session:
        with pytest.raises(BetsClosed):
            await betting.place_bet(session, game, ALICE, BetSide.WIN, 10)


async def test_cancel_returns_the_stake(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 400)
        await session.commit()

    async with session_factory() as session:
        _, wallet = await betting.cancel_bet(session, game, ALICE)
        await session.commit()

    assert wallet.balance == 1000
    assert wallet.total_wagered == 0

    async with session_factory() as session:
        assert await betting.get_bet(session, game.id, ALICE) is None


async def test_cancel_is_refused_after_lock(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await session.commit()

    async with session_factory() as session:
        locked = await session.get(TrackedGame, game.id)
        locked.status = GameStatus.LOCKED
        with pytest.raises(BetsClosed):
            await betting.cancel_bet(session, locked, ALICE)


# -- settlement ------------------------------------------------------------


async def test_winners_split_the_whole_pool(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await betting.place_bet(session, game, BOB, BetSide.WIN, 100)
        await betting.place_bet(session, game, CAROL, BetSide.LOSS, 200)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    assert settlement.winning_side == BetSide.WIN
    assert settlement.pool.total == 400
    assert settlement.total_paid == 400  # 0% rake, nothing evaporates
    assert {payout for _, _, payout in settlement.paid} == {200}

    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
        carol = await betting.get_wallet(session, GUILD, CAROL)
    assert alice.balance == 900 + 200  # 1000 - 100 stake + 200 payout
    assert alice.bets_won == 1
    assert alice.net_profit == 100
    assert carol.balance == 800
    assert carol.bets_lost == 1
    assert carol.net_profit == -200


async def test_a_lone_winner_takes_everything(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.LOSS, 50)
        await betting.place_bet(session, game, BOB, BetSide.WIN, 450)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=False)
        await session.commit()

    assert settlement.total_paid == 500
    assert settlement.paid[0][0] == ALICE


async def test_nobody_on_the_winning_side_loses_everything(session_factory, betting):
    """Se tromper a plusieurs du meme cote doit couter, pas etre rembourse."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 300)
        await betting.place_bet(session, game, BOB, BetSide.WIN, 200)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=False)
        await session.commit()

    assert settlement.refunded is False
    assert settlement.paid == []
    assert len(settlement.lost) == 2
    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
    assert alice.balance == 700  # 1000 - 300 mises, rien ne revient
    assert alice.net_profit == -300


async def test_a_lone_correct_bettor_still_gains(session_factory, betting):
    """Sans la banque, le parimutuel rendrait exactement la mise : x1.00."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    payout = settlement.paid[0][2]
    assert payout == 120  # plancher x1.20 comble par la banque
    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
    assert alice.balance == 1020
    assert alice.net_profit == 20


async def test_everyone_on_the_winning_side_still_gains(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await betting.place_bet(session, game, BOB, BetSide.WIN, 400)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    payouts = {user: payout for user, _, payout in settlement.paid}
    assert payouts[ALICE] == 120
    assert payouts[BOB] == 480


async def test_the_floor_never_lowers_a_better_payout(session_factory, betting):
    """Quand les perdants ont alimente la cagnotte, le parimutuel prime."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await betting.place_bet(session, game, BOB, BetSide.LOSS, 900)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    # 1000 de cagnotte pour 100 mises du bon cote : x10, bien au-dessus de x1.2
    assert settlement.paid[0][2] == 1000


def test_the_displayed_odds_respect_the_floor():
    """La cote annoncee doit etre celle qui sera payee."""
    lonely = Pool(win_amount=500, loss_amount=0, win_count=1, min_multiplier=1.2)
    assert lonely.multiplier(BetSide.WIN) == pytest.approx(1.2)

    contested = Pool(win_amount=100, loss_amount=900, win_count=1, loss_count=1,
                     min_multiplier=1.2)
    assert contested.multiplier(BetSide.WIN) == pytest.approx(10.0)


def test_a_side_with_no_bets_has_no_odds_yet():
    empty = Pool(win_amount=100, loss_amount=0, win_count=1, min_multiplier=1.2)
    assert empty.multiplier(BetSide.LOSS) is None


async def test_void_refunds_every_bet(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 120)
        await betting.place_bet(session, game, BOB, BetSide.LOSS, 80)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.refund_all(session, stored)
        await session.commit()

    assert settlement.refunded is True
    async with session_factory() as session:
        for user in (ALICE, BOB):
            wallet = await betting.get_wallet(session, GUILD, user)
            assert wallet.balance == 1000


async def test_settlement_does_not_pay_twice(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await betting.place_bet(session, game, BOB, BetSide.LOSS, 100)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        second = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    assert second.paid == []  # already settled bets are skipped
    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
    assert alice.balance == 1100


# -- daily -----------------------------------------------------------------


async def test_daily_grants_then_goes_on_cooldown(session_factory, betting):
    async with session_factory() as session:
        amount, remaining = await betting.claim_daily(session, GUILD, ALICE)
        await session.commit()
    assert amount == 100
    assert remaining is None

    async with session_factory() as session:
        amount, remaining = await betting.claim_daily(session, GUILD, ALICE)
        await session.commit()
    assert amount == 0
    assert remaining is not None and remaining.total_seconds() > 0


async def test_leaderboard_is_sorted_by_balance(session_factory, betting):
    async with session_factory() as session:
        for user, balance in ((ALICE, 500), (BOB, 2500), (CAROL, 1500)):
            wallet = await betting.get_wallet(session, GUILD, user)
            wallet.balance = balance
            session.add(wallet)
        await session.commit()

    async with session_factory() as session:
        top = await betting.leaderboard(session, GUILD)

    assert [wallet.user_id for wallet in top] == [BOB, CAROL, ALICE]
