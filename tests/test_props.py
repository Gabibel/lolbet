"""Paris annexes : plus ou moins de N morts pour un joueur.

C'est le seul des quatre ajouts qui déplace des pièces, donc c'est celui qui
mérite le plus de tests. Les règles vérifiées :

* la ligne est toujours en demi-point, donc aucune égalité possible ;
* la ligne se fige au premier pari, sinon deux parieurs joueraient contre des
  lignes différentes sur le même marché ;
* la cote est lue avant que la mise n'entre dans le pool, sinon on
  déplacerait sa propre cote ;
* un remake rend tout, et un joueur absent du match est remboursé plutôt que
  jugé sur une donnée manquante.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

import pytest

from lolbet.models import (
    GameStatus,
    PlayerGameStat,
    PropPick,
    SideBet,
    TrackedGame,
    TrackedParticipant,
)
from lolbet.services.betting import BetsClosed, DuplicateBet, InsufficientFunds
from lolbet.services.props import (
    DEFAULT_LINE,
    PropService,
    UnknownTarget,
    describe,
    round_to_half,
    suggest_line,
)
from lolbet.utils import utcnow

GUILD = 777
ALICE, BOB = 11, 22
TARGET = "puuid-cible"


@pytest.fixture
def props(settings, betting) -> PropService:
    return PropService(settings, betting)


_counter = iter(range(1, 10_000))


async def make_game(
    session_factory, *, status=GameStatus.LIVE, lock_in=300, riot_id: str | None = None
) -> TrackedGame:
    async with session_factory() as session:
        game = TrackedGame(
            guild_id=GUILD,
            riot_game_id=riot_id or f"EUW1_9{next(_counter):04d}",
            platform="euw1",
            queue_id=420,
            status=status,
            tracked_team_id=100,
            game_start_at=utcnow(),
            lock_at=utcnow() + timedelta(seconds=lock_in),
            channel_id=1,
        )
        session.add(game)
        await session.flush()
        session.add(
            TrackedParticipant(
                game_id=int(game.id or 0),
                puuid=TARGET,
                discord_id=99,
                riot_id="Cible#EUW",
                team_id=100,
            )
        )
        await session.commit()
        return game


async def history(session_factory, deaths: list[int]) -> None:
    """Des parties passées, une par ligne : UNIQUE(game_id, puuid) l'impose."""
    async with session_factory() as session:
        for index, count in enumerate(deaths):
            past = TrackedGame(
                guild_id=GUILD,
                riot_game_id=f"EUW1_h{next(_counter):04d}",
                platform="euw1",
                status=GameStatus.RESOLVED,
                tracked_team_id=100,
            )
            session.add(past)
            await session.flush()
            session.add(
                PlayerGameStat(
                    game_id=int(past.id or 0),
                    guild_id=GUILD,
                    discord_id=99,
                    puuid=TARGET,
                    riot_game_id=past.riot_game_id,
                    deaths=count,
                    played_at=utcnow() - timedelta(days=index + 1),
                )
            )
        await session.commit()


# -- la ligne --------------------------------------------------------------


def test_the_line_is_never_a_whole_number():
    """Une ligne entière autoriserait l'égalité, donc un litige."""
    for value in (0.0, 3.0, 6.4, 6.6, 12.9):
        assert round_to_half(value) % 1 == 0.5


async def test_without_history_the_line_is_the_default(session_factory):
    async with session_factory() as session:
        assert await suggest_line(session, GUILD, TARGET) == DEFAULT_LINE


async def test_the_line_follows_the_recent_average(session_factory):
    await history(session_factory, [8, 9, 7])  # moyenne 8
    async with session_factory() as session:
        assert await suggest_line(session, GUILD, TARGET) == 8.5


async def test_the_line_stays_inside_sane_bounds(session_factory):
    await history(session_factory, [40, 45, 50])
    async with session_factory() as session:
        assert await suggest_line(session, GUILD, TARGET) == 14.5


async def test_the_line_freezes_on_the_first_bet(session_factory, props):
    """Sinon le deuxième parieur jouerait contre une autre ligne."""
    await history(session_factory, [3, 3, 3])  # ligne 3.5
    game = await make_game(session_factory)

    async with session_factory() as session:
        await props.place(session, game, ALICE, TARGET, PropPick.OVER, 100)
        await session.commit()

    # L'historique change, la ligne du marché ne doit pas bouger.
    await history(session_factory, [20, 20, 20])
    async with session_factory() as session:
        assert await props.line_for(session, game, TARGET) == 3.5


# -- placer un pari --------------------------------------------------------


async def test_placing_a_bet_moves_the_coins_out_of_the_wallet(session_factory, props, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        bet, wallet = await props.place(session, game, ALICE, TARGET, PropPick.OVER, 300)
        await session.commit()
        assert wallet.balance == 700
        assert bet.amount == 300
        assert bet.odds > 1


async def test_the_odds_are_read_before_the_stake_lands(session_factory, props):
    """Miser ne doit pas déplacer sa propre cote."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        first, _ = await props.place(session, game, ALICE, TARGET, PropPick.OVER, 500)
        await session.commit()
    async with session_factory() as session:
        pool = await props.pool(session, int(game.id or 0), TARGET)
    # Le camp charge paie moins, l'autre paie plus.
    assert pool.over_odds < first.odds
    assert pool.under_odds > first.odds


async def test_two_bets_on_the_same_target_are_refused(session_factory, props):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await props.place(session, game, ALICE, TARGET, PropPick.OVER, 100)
        await session.commit()
    async with session_factory() as session:
        with pytest.raises(DuplicateBet):
            await props.place(session, game, ALICE, TARGET, PropPick.UNDER, 100)


async def test_betting_on_someone_not_in_the_game_is_refused(session_factory, props):
    game = await make_game(session_factory)
    async with session_factory() as session:
        with pytest.raises(UnknownTarget):
            await props.place(session, game, ALICE, "inconnu", PropPick.OVER, 100)


async def test_a_locked_game_takes_no_more_bets(session_factory, props):
    game = await make_game(session_factory, status=GameStatus.LOCKED)
    async with session_factory() as session:
        with pytest.raises(BetsClosed):
            await props.place(session, game, ALICE, TARGET, PropPick.OVER, 100)


async def test_you_cannot_bet_more_than_you_have(session_factory, props):
    game = await make_game(session_factory)
    async with session_factory() as session:
        with pytest.raises(InsufficientFunds):
            await props.place(session, game, ALICE, TARGET, PropPick.OVER, 99_999)


async def test_cancelling_gives_the_stake_back(session_factory, props, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await props.place(session, game, ALICE, TARGET, PropPick.OVER, 400)
        await session.commit()
    async with session_factory() as session:
        await props.cancel(session, game, ALICE, TARGET)
        await session.commit()
    async with session_factory() as session:
        wallet = await betting.get_wallet(session, GUILD, ALICE)
    assert wallet.balance == 1000


# -- règlement -------------------------------------------------------------


async def settle_with(session_factory, props, deaths: int):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await props.place(session, game, ALICE, TARGET, PropPick.OVER, 200)
        await props.place(session, game, BOB, TARGET, PropPick.UNDER, 200)
        await session.commit()
    async with session_factory() as session:
        settlement = await props.settle(session, game, {TARGET: deaths})
        await session.commit()
    return game, settlement


async def test_over_wins_when_the_count_beats_the_line(session_factory, props, betting):
    _, settlement = await settle_with(session_factory, props, deaths=12)
    assert [user for user, _, _ in settlement.paid] == [ALICE]
    assert [user for user, _ in settlement.lost] == [BOB]

    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
        bob = await betting.get_wallet(session, GUILD, BOB)
    assert alice.balance > 800  # mise rendue plus le gain
    assert bob.balance == 800  # mise perdue
    assert (alice.bets_won, bob.bets_lost) == (1, 1)


async def test_under_wins_when_the_count_falls_short(session_factory, props):
    _, settlement = await settle_with(session_factory, props, deaths=2)
    assert [user for user, _, _ in settlement.paid] == [BOB]
    assert [user for user, _ in settlement.lost] == [ALICE]


async def test_the_line_being_a_half_point_removes_every_tie(session_factory, props):
    """Sur la ligne par défaut de 6.5, six et sept départagent toujours."""
    _, six = await settle_with(session_factory, props, deaths=6)
    _, seven = await settle_with(session_factory, props, deaths=7)
    assert len(six.paid) == 1 and len(six.lost) == 1
    assert len(seven.paid) == 1 and len(seven.lost) == 1


async def test_settling_twice_pays_only_once(session_factory, props, betting):
    game, _ = await settle_with(session_factory, props, deaths=12)
    async with session_factory() as session:
        alice_before = (await betting.get_wallet(session, GUILD, ALICE)).balance

    async with session_factory() as session:
        again = await props.settle(session, game, {TARGET: 12})
        await session.commit()
    assert again.paid == [] and again.lost == []

    async with session_factory() as session:
        assert (await betting.get_wallet(session, GUILD, ALICE)).balance == alice_before


async def test_a_target_missing_from_the_match_is_refunded(session_factory, props, betting):
    """Trancher sur une donnée absente serait pire que rendre la mise."""
    game = await make_game(session_factory)
    async with session_factory() as session:
        await props.place(session, game, ALICE, TARGET, PropPick.OVER, 250)
        await session.commit()
    async with session_factory() as session:
        settlement = await props.settle(session, game, {})
        await session.commit()

    assert settlement.lost == []
    async with session_factory() as session:
        wallet = await betting.get_wallet(session, GUILD, ALICE)
    assert wallet.balance == 1000
    assert wallet.bets_won == 0 and wallet.bets_lost == 0


async def test_a_remake_gives_every_side_bet_back(session_factory, props, betting):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await props.place(session, game, ALICE, TARGET, PropPick.OVER, 300)
        await props.place(session, game, BOB, TARGET, PropPick.UNDER, 150)
        await session.commit()

    async with session_factory() as session:
        settlement = await props.refund_all(session, game)
        await session.commit()

    assert settlement.refunded
    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
        bob = await betting.get_wallet(session, GUILD, BOB)
    assert (alice.balance, bob.balance) == (1000, 1000)
    assert (alice.bets_won, alice.bets_lost) == (0, 0)


async def test_the_actual_count_is_kept_for_the_recap(session_factory, props):
    game, _ = await settle_with(session_factory, props, deaths=12)
    async with session_factory() as session:
        bets = list(
            (
                await session.execute(select(SideBet).where(SideBet.game_id == game.id))
            ).scalars()
        )
    assert all(bet.actual == 12 for bet in bets)


# -- rendu -----------------------------------------------------------------


async def test_the_description_reads_like_a_sentence(session_factory, props):
    game = await make_game(session_factory)
    async with session_factory() as session:
        bet, _ = await props.place(session, game, ALICE, TARGET, PropPick.OVER, 100)
        await session.commit()
    assert describe(bet) == "PLUS de 6.5 morts pour Cible#EUW"


async def test_open_bets_are_listed_for_the_player(session_factory, props):
    game = await make_game(session_factory)
    async with session_factory() as session:
        await props.place(session, game, ALICE, TARGET, PropPick.OVER, 100)
        await session.commit()
    async with session_factory() as session:
        mine = await props.open_bets_for(session, GUILD, ALICE)
        theirs = await props.open_bets_for(session, GUILD, BOB)
    assert len(mine) == 1
    assert theirs == []
