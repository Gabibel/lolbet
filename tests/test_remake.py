"""Une partie abandonnée n'est pas un résultat.

Riot désigne quand même une équipe gagnante sur un remake : sans détection,
le bot réglerait les paris sur trois minutes de jeu que personne n'a jouées.
"""

from __future__ import annotations

from lolbet.models import BetSide, GameStatus
from lolbet.services.embeds import build_remake_embed
from lolbet.services.scoring import REMAKE_MAX_SECONDS, is_remake

from test_scoring import build_match, default_roster, participant

GUILD = 700
ALICE, BOB = 11, 22


# -- détection -------------------------------------------------------------


def test_a_normal_game_is_not_a_remake():
    assert is_remake(build_match(default_roster(), duration=1800)) is False


def test_the_early_surrender_flag_wins_over_everything():
    """Le champ de Riot fait foi, même sur une partie longue."""
    roster = default_roster()
    for player in roster:
        player["gameEndedInEarlySurrender"] = True
    assert is_remake(build_match(roster, duration=1800)) is True


def test_a_three_minute_game_is_a_remake():
    assert is_remake(build_match(default_roster(), duration=180)) is True


def test_the_boundary_is_five_minutes():
    just_under = build_match(default_roster(), duration=REMAKE_MAX_SECONDS - 1)
    exactly = build_match(default_roster(), duration=REMAKE_MAX_SECONDS)
    assert is_remake(just_under) is True
    assert is_remake(exactly) is False


def test_a_legacy_millisecond_duration_is_understood():
    """Avant le patch 11.20, gameDuration était en millisecondes.

    Ces vieux matchs n'ont pas de ``gameEndTimestamp`` : c'est ce qui permet
    de reconnaître l'ancienne unité.
    """
    old = build_match(default_roster(), duration=180_000)
    old["info"].pop("gameEndTimestamp")
    assert is_remake(old) is True

    long_one = build_match(default_roster(), duration=1_800_000)
    long_one["info"].pop("gameEndTimestamp")
    assert is_remake(long_one) is False


def test_an_empty_match_is_not_called_a_remake():
    """Sans participants, on ne sait rien : mieux vaut ne rien affirmer."""
    assert is_remake({"info": {"gameDuration": 0, "participants": []}}) is False
    assert is_remake({}) is False


def test_one_flagged_participant_is_enough():
    roster = default_roster()
    roster[0]["gameEndedInEarlySurrender"] = True
    assert is_remake(build_match(roster, duration=1800)) is True


def test_a_full_length_game_with_the_flag_false_is_kept():
    roster = [
        participant(puuid=f"p{i}", team=100 if i < 5 else 200, position="MIDDLE", win=i < 5)
        for i in range(10)
    ]
    for player in roster:
        player["gameEndedInEarlySurrender"] = False
    assert is_remake(build_match(roster, duration=2400)) is False


# -- remboursement ---------------------------------------------------------


async def test_a_remake_gives_every_coin_back(session_factory, betting):
    """Le cas qui compte : deux paris opposés, tout le monde récupère sa mise."""
    from datetime import timedelta

    from lolbet.models import TrackedGame
    from lolbet.utils import utcnow

    async with session_factory() as session:
        game = TrackedGame(
            guild_id=GUILD,
            riot_game_id="EUW1_7974771166",
            platform="euw1",
            queue_id=420,
            status=GameStatus.LIVE,
            tracked_team_id=100,
            game_start_at=utcnow(),
            lock_at=utcnow() + timedelta(seconds=300),
            channel_id=123,
        )
        session.add(game)
        await session.flush()
        await betting.place_bet(session, game, ALICE, BetSide.WIN, 300)
        await betting.place_bet(session, game, BOB, BetSide.LOSS, 200)
        game.status = GameStatus.PENDING_RESULT
        session.add(game)
        await session.commit()
        game_id = int(game.id or 0)

    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
        bob = await betting.get_wallet(session, GUILD, BOB)
        assert alice.balance == 700
        assert bob.balance == 800

    async with session_factory() as session:
        game = await session.get(TrackedGame, game_id)
        settlement = await betting.refund_all(session, game)
        game.status = GameStatus.VOID
        session.add(game)
        await session.commit()

    assert settlement.pool.count == 2
    assert settlement.pool.total == 500

    async with session_factory() as session:
        alice = await betting.get_wallet(session, GUILD, ALICE)
        bob = await betting.get_wallet(session, GUILD, BOB)
    assert alice.balance == 1000
    assert bob.balance == 1000
    # Un remboursement n'est ni une victoire ni une defaite.
    assert (alice.bets_won, alice.bets_lost) == (0, 0)
    assert (bob.bets_won, bob.bets_lost) == (0, 0)


def test_the_remake_message_says_what_was_given_back(betting):
    from lolbet.services.betting import Pool, Settlement

    pool = Pool(win_amount=300, loss_amount=200, win_count=1, loss_count=1)
    settlement = Settlement(
        winning_side=None, pool=pool, paid=[], lost=[], refunded=True
    )
    embed = build_remake_embed("EUW1_7974771166", settlement)
    rendered = embed.to_dict()
    assert "Remake" in rendered["title"]
    assert "rendues" in rendered["description"]
    assert any("500" in field["value"] for field in rendered.get("fields", []))


def test_the_remake_message_stands_alone_without_bets():
    embed = build_remake_embed("EUW1_7974771166", None)
    assert embed.to_dict().get("fields", []) == []
