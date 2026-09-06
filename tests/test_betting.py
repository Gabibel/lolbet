"""Cotes à la bookmaker, et cycle de vie du portefeuille."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lolbet.models import Bet, BetSide, GameStatus, TrackedGame
from lolbet.services.betting import (
    BetsClosed,
    DuplicateBet,
    InsufficientFunds,
    InvalidAmount,
    Pool,
    compute_odds,
)
from lolbet.utils import utcnow

GUILD = 1234
ALICE, BOB, CAROL = 11, 22, 33

# Les réglages par défaut, repris ici pour que les valeurs attendues soient
# lisibles sans aller les chercher.
ODDS = {"seed": 100, "margin": 0.05, "minimum": 1.05, "maximum": 10.0}


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


async def bet_of(session_factory, game_id: int, user_id: int) -> Bet:
    async with session_factory() as session:
        from sqlalchemy import select

        return (
            await session.execute(
                select(Bet).where(Bet.game_id == game_id, Bet.user_id == user_id)
            )
        ).scalar_one()


# -- la cote --------------------------------------------------------------


def test_an_empty_market_opens_symmetrically():
    """Personne n'a misé : les deux camps paient pareil."""
    assert compute_odds(0, 0, **ODDS) == pytest.approx(1.9)


def test_money_on_a_side_lowers_its_odds():
    """C'est tout l'intérêt : la cote suit l'argent."""
    loaded = compute_odds(500, 500, **ODDS)
    light = compute_odds(0, 500, **ODDS)
    assert loaded < 1.9 < light
    assert loaded == pytest.approx(1.11)
    assert light == pytest.approx(6.65)


def test_odds_move_step_by_step():
    steps = [compute_odds(amount, amount, **ODDS) for amount in (0, 100, 200, 500)]
    assert steps == sorted(steps, reverse=True)  # de plus en plus chargé, paie de moins en moins


def test_a_balanced_market_is_back_to_even():
    assert compute_odds(500, 1000, **ODDS) == pytest.approx(1.9)


def test_odds_are_clamped():
    assert compute_odds(0, 10**9, **ODDS) == 10.0
    assert compute_odds(10**9, 10**9, **ODDS) == 1.05


def test_the_margin_is_what_the_house_keeps():
    fair = compute_odds(0, 0, **{**ODDS, "margin": 0.0})
    with_margin = compute_odds(0, 0, **ODDS)
    assert fair == pytest.approx(2.0)
    assert with_margin < fair


def test_the_seed_decides_how_fast_odds_move():
    """Une petite mise virtuelle rend le marché plus nerveux."""
    nervous = compute_odds(100, 100, **{**ODDS, "seed": 10})
    calm = compute_odds(100, 100, **{**ODDS, "seed": 1000})
    assert nervous < calm


def test_pool_exposes_its_odds_and_implied_probability():
    pool = Pool(
        win_amount=300, loss_amount=100, win_count=2, loss_count=1,
        win_odds=1.42, loss_odds=2.85,
    )
    assert pool.total == 400
    assert pool.multiplier(BetSide.WIN) == pytest.approx(1.42)
    assert pool.multiplier(BetSide.LOSS) == pytest.approx(2.85)
    assert pool.implied_probability(BetSide.WIN) == pytest.approx(0.75)


def test_a_pool_without_odds_reports_none():
    assert Pool().multiplier(BetSide.WIN) is None


# -- placer un pari --------------------------------------------------------


async def test_place_bet_moves_coins_into_escrow(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        bet, wallet = await betting.place_bet(session, game, ALICE, BetSide.WIN, 250)
        await session.commit()

    assert bet.amount == 250
    assert wallet.balance == 750
    assert wallet.total_wagered == 250


async def test_the_odds_are_frozen_when_the_bet_is_placed(session_factory, betting):
    """Le premier parieur garde 1.90 même quand la cote descend ensuite."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await session.commit()
    async with session_factory() as session:
        await betting.place_bet(session, game, BOB, BetSide.WIN, 100)
        await session.commit()

    alice = await bet_of(session_factory, game.id, ALICE)
    bob = await bet_of(session_factory, game.id, BOB)
    assert alice.odds == pytest.approx(1.9)
    assert bob.odds == pytest.approx(1.42)  # le camp s'est chargé entre-temps


async def test_your_own_bet_does_not_move_your_own_odds(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 5000 // 10)
        await session.commit()
    alice = await bet_of(session_factory, game.id, ALICE)
    assert alice.odds == pytest.approx(1.9)


async def test_betting_against_the_crowd_pays_more(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 500)
        await session.commit()
    async with session_factory() as session:
        await betting.place_bet(session, game, BOB, BetSide.LOSS, 100)
        await session.commit()

    alice = await bet_of(session_factory, game.id, ALICE)
    bob = await bet_of(session_factory, game.id, BOB)
    assert bob.odds > alice.odds


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


# -- règlement -------------------------------------------------------------


async def test_each_winner_is_paid_at_his_own_odds(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)  # 1.90
        await session.commit()
    async with session_factory() as session:
        await betting.place_bet(session, game, BOB, BetSide.WIN, 100)  # 1.42
        await session.commit()
    async with session_factory() as session:
        await betting.place_bet(session, game, CAROL, BetSide.LOSS, 200)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    payouts = {user: payout for user, _, payout in settlement.paid}
    assert payouts[ALICE] == 190
    assert payouts[BOB] == 142

    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
        carol = await betting.get_wallet(session, GUILD, CAROL)
    assert alice.balance == 900 + 190
    assert alice.net_profit == 90
    assert carol.balance == 800
    assert carol.bets_lost == 1
    assert carol.net_profit == -200


async def test_a_lone_bettor_who_is_right_gains(session_factory, betting):
    """Le cas qui ne rapportait rien en parimutuel."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await session.commit()
    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    assert settlement.paid[0][2] == 190
    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
    assert alice.balance == 1090


async def test_a_lone_bettor_who_is_wrong_loses(session_factory, betting):
    """Et celui qui était remboursé auparavant."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await session.commit()
    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=False)
        await session.commit()

    assert settlement.paid == []
    assert settlement.refunded is False
    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
    assert alice.balance == 900
    assert alice.net_profit == -100


async def test_everyone_on_the_same_losing_side_loses(session_factory, betting):
    """Deux joueurs, même camp, mauvais choix : plus de remboursement."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 300)
        await session.commit()
    async with session_factory() as session:
        await betting.place_bet(session, game, BOB, BetSide.WIN, 200)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=False)
        await session.commit()

    assert settlement.paid == []
    assert len(settlement.lost) == 2
    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
    assert alice.balance == 700


async def test_everyone_on_the_same_winning_side_gains(session_factory, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await session.commit()
    async with session_factory() as session:
        await betting.place_bet(session, game, BOB, BetSide.WIN, 100)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    assert all(payout > stake for _, stake, payout in settlement.paid)


async def test_a_bet_without_stored_odds_falls_back(session_factory, betting):
    """Les paris d'avant la migration n'ont pas de cote enregistrée."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 100)
        await session.commit()
    async with session_factory() as session:
        legacy = await betting.get_bet(session, game.id, ALICE)
        legacy.odds = 0.0
        session.add(legacy)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        settlement = await betting.settle(session, stored, tracked_team_won=True)
        await session.commit()

    assert settlement.paid[0][2] == 105  # cote minimale, jamais moins que la mise


async def test_void_still_refunds_everyone(session_factory, betting):
    """Une partie annulée n'est pas un résultat : tout est rendu."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 120)
        await session.commit()
    async with session_factory() as session:
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
        await session.commit()
    async with session_factory() as session:
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

    assert second.paid == []
    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
    assert alice.balance == 900 + 190


# -- quotidien et classement ----------------------------------------------


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
