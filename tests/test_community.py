"""Bilan hebdomadaire, trophées et face-à-face.

Trois lectures sur des données figées au règlement. Ce qui est vérifié ici,
c'est surtout ce que le bot n'a pas le droit d'affirmer : pas de LP inventé
quand rien ne permet de le mesurer, pas de face-à-face annoncé entre deux
joueurs qui n'ont jamais joué ensemble.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from lolbet.models import (
    Bet,
    BetSide,
    GameStatus,
    PlayerGameStat,
    RankSnapshot,
    TrackedGame,
    TrackedParticipant,
)
from lolbet.services.awards import (
    Records,
    missing_for,
    player_games,
    records_for,
    trophies_for,
)
from lolbet.services.digest import build_digest, is_due, next_occurrence, timezone_or_utc
from lolbet.services.headtohead import compare
from lolbet.utils import utcnow

GUILD = 4242
ALICE, BOB = 11, 22
TZ = timezone_or_utc("Europe/Paris")


async def add_game(
    session_factory,
    *,
    riot_id: str,
    players: list[tuple[int, str, dict]],
    days_ago: float = 1.0,
    teams: dict[int, int] | None = None,
) -> int:
    """Une partie suivie et les lignes de statistiques associées."""
    played = utcnow() - timedelta(days=days_ago)
    async with session_factory() as session:
        game = TrackedGame(
            guild_id=GUILD,
            riot_game_id=riot_id,
            platform="euw1",
            queue_id=420,
            status=GameStatus.RESOLVED,
            tracked_team_id=100,
        )
        session.add(game)
        await session.flush()
        game_id = int(game.id or 0)

        for discord_id, puuid, stats in players:
            session.add(
                TrackedParticipant(
                    game_id=game_id,
                    puuid=puuid,
                    discord_id=discord_id,
                    riot_id=f"J{discord_id}#EUW",
                    team_id=(teams or {}).get(discord_id, 100),
                )
            )
            session.add(
                PlayerGameStat(
                    game_id=game_id,
                    guild_id=GUILD,
                    discord_id=discord_id,
                    puuid=puuid,
                    riot_game_id=riot_id,
                    played_at=played,
                    duration_seconds=stats.get("duration", 1800),
                    champion_name=stats.get("champion", "LeeSin"),
                    win=stats.get("win", False),
                    kills=stats.get("kills", 3),
                    deaths=stats.get("deaths", 3),
                    assists=stats.get("assists", 3),
                    cs=stats.get("cs", 150),
                    vision_score=stats.get("vision", 20),
                    score=stats.get("score", 40.0),
                    is_mvp=stats.get("mvp", False),
                    is_lvp=stats.get("lvp", False),
                )
            )
        await session.commit()
        return game_id


# -- planification ---------------------------------------------------------


def test_the_slot_is_the_next_matching_weekday():
    lundi = datetime(2026, 9, 7, 14, 0, tzinfo=TZ)
    prochain = next_occurrence(lundi, 6, 20, tzinfo=TZ)
    assert prochain.weekday() == 6
    assert prochain.hour == 20
    assert prochain > lundi


def test_a_fresh_install_does_not_post_immediately():
    """Sans repère, le bot attend le vrai créneau au lieu de rattraper."""
    lundi = datetime(2026, 9, 7, 14, 0, tzinfo=TZ)
    assert is_due(lundi, None, 6, 20, tzinfo=TZ) is False


def test_an_elapsed_slot_is_served_once():
    lundi = datetime(2026, 9, 7, 14, 0, tzinfo=TZ)
    avant = datetime(2026, 9, 6, 14, 0, tzinfo=TZ)  # dimanche, avant 20h
    apres = datetime(2026, 9, 6, 21, 0, tzinfo=TZ)  # dimanche, après 20h
    assert is_due(lundi, avant, 6, 20, tzinfo=TZ) is True
    assert is_due(lundi, apres, 6, 20, tzinfo=TZ) is False


def test_a_long_outage_still_only_owes_one_digest():
    lundi = datetime(2026, 9, 7, 14, 0, tzinfo=TZ)
    vieux = datetime(2026, 8, 10, 12, 0, tzinfo=TZ)
    assert is_due(lundi, vieux, 6, 20, tzinfo=TZ) is True


def test_an_unknown_timezone_falls_back_instead_of_crashing():
    """Un fuseau mal saisi doit décaler l'heure, pas arrêter le bot."""
    assert timezone_or_utc("Mars/Olympus") is not None


# -- bilan -----------------------------------------------------------------


async def test_an_empty_week_is_still_a_valid_digest(session_factory):
    async with session_factory() as session:
        digest = await build_digest(session, GUILD)
    assert digest.has_data is False
    assert digest.games == 0


async def test_the_digest_counts_distinct_games_not_stat_rows(session_factory):
    """Deux joueurs suivis dans une partie, c'est une partie, pas deux."""
    await add_game(
        session_factory,
        riot_id="EUW1_1",
        players=[(ALICE, "pa", {"win": True}), (BOB, "pb", {"win": True})],
    )
    async with session_factory() as session:
        digest = await build_digest(session, GUILD)
    assert digest.games == 1
    assert len(digest.players) == 2


async def test_games_outside_the_window_are_ignored(session_factory):
    await add_game(session_factory, riot_id="EUW1_1", players=[(ALICE, "pa", {})], days_ago=2)
    await add_game(session_factory, riot_id="EUW1_2", players=[(ALICE, "pa", {})], days_ago=30)
    async with session_factory() as session:
        digest = await build_digest(session, GUILD, days=7)
    assert digest.games == 1


async def test_lp_is_none_when_nothing_measures_it(session_factory):
    """Aucun relevé de rang : on affiche un tiret, jamais un zéro."""
    await add_game(session_factory, riot_id="EUW1_1", players=[(ALICE, "pa", {})])
    async with session_factory() as session:
        digest = await build_digest(session, GUILD)
    assert digest.players[0].lp is None
    assert digest.climber is None
    assert digest.faller is None


async def test_lp_is_measured_when_two_snapshots_exist(session_factory):
    await add_game(session_factory, riot_id="EUW1_1", players=[(ALICE, "pa", {})])
    async with session_factory() as session:
        for lp, days in ((20, 9), (68, 0.2)):
            session.add(
                RankSnapshot(
                    puuid="pa",
                    platform="euw1",
                    tier="GOLD",
                    division="IV",
                    league_points=lp,
                    ladder_score=1200 + lp,
                    captured_at=utcnow() - timedelta(days=days),
                )
            )
        await session.commit()

    async with session_factory() as session:
        digest = await build_digest(session, GUILD)
    assert digest.players[0].lp == 48
    assert digest.climber is not None


async def test_the_best_and_worst_games_are_the_extremes(session_factory):
    await add_game(
        session_factory,
        riot_id="EUW1_1",
        players=[
            (ALICE, "pa", {"score": 90.0, "kills": 15}),
            (BOB, "pb", {"score": 5.0, "deaths": 14}),
        ],
    )
    async with session_factory() as session:
        digest = await build_digest(session, GUILD)
    assert digest.best_game.discord_id == ALICE
    assert digest.worst_game.discord_id == BOB
    assert digest.feeder.discord_id == BOB


async def test_the_bettors_ranking_uses_settled_bets_only(session_factory):
    game_id = await add_game(
        session_factory, riot_id="EUW1_1", players=[(ALICE, "pa", {})]
    )
    async with session_factory() as session:
        session.add(
            Bet(
                game_id=game_id,
                guild_id=GUILD,
                user_id=ALICE,
                side=BetSide.WIN,
                amount=100,
                payout=250,
                settled_at=utcnow(),
            )
        )
        # Non réglé : ne doit pas compter.
        session.add(
            Bet(
                game_id=game_id,
                guild_id=GUILD,
                user_id=BOB,
                side=BetSide.LOSS,
                amount=500,
            )
        )
        await session.commit()

    async with session_factory() as session:
        digest = await build_digest(session, GUILD)
    assert [b.user_id for b in digest.bettors] == [ALICE]
    assert digest.bettors[0].profit == 150


# -- trophées --------------------------------------------------------------


async def test_a_newcomer_has_records_but_no_history(session_factory):
    async with session_factory() as session:
        games = await player_games(session, GUILD, ALICE)
    assert games == []
    assert records_for(games) == Records()
    assert trophies_for(games) == []


async def test_a_trophy_is_earned_only_when_the_threshold_is_passed(session_factory):
    await add_game(session_factory, riot_id="EUW1_1", players=[(ALICE, "pa", {"deaths": 5})])
    async with session_factory() as session:
        games = await player_games(session, GUILD, ALICE)
    keys = {t.key for t in trophies_for(games)}
    assert "first_blood" in keys
    assert "feeder" not in keys  # 5 morts, il en faut 12

    await add_game(session_factory, riot_id="EUW1_2", players=[(ALICE, "pa", {"deaths": 13})])
    async with session_factory() as session:
        games = await player_games(session, GUILD, ALICE)
    assert "feeder" in {t.key for t in trophies_for(games)}


async def test_a_losing_streak_is_measured_over_the_whole_history(session_factory):
    for index in range(4):
        await add_game(
            session_factory,
            riot_id=f"EUW1_{index}",
            players=[(ALICE, "pa", {"win": False})],
            days_ago=10 - index,
        )
    async with session_factory() as session:
        games = await player_games(session, GUILD, ALICE)
    records = records_for(games)
    assert records.worst_loss_streak == 4
    assert records.best_win_streak == 0
    assert "cold_streak" in {t.key for t in trophies_for(games)}


async def test_missing_trophies_are_the_ones_not_earned(session_factory):
    await add_game(session_factory, riot_id="EUW1_1", players=[(ALICE, "pa", {})])
    async with session_factory() as session:
        games = await player_games(session, GUILD, ALICE)
    earned = {t.label for t in trophies_for(games)}
    assert earned.isdisjoint(set(missing_for(games)))


async def test_a_short_game_without_deaths_is_not_a_clean_sheet(session_factory):
    """Ne pas mourir en huit minutes ne prouve rien : c'est un remake."""
    await add_game(
        session_factory,
        riot_id="EUW1_1",
        players=[(ALICE, "pa", {"deaths": 0, "duration": 480})],
    )
    async with session_factory() as session:
        games = await player_games(session, GUILD, ALICE)
    assert "deathless" not in {t.key for t in trophies_for(games)}


# -- face-à-face -----------------------------------------------------------


async def test_two_players_who_never_met_have_no_head_to_head(session_factory):
    await add_game(session_factory, riot_id="EUW1_1", players=[(ALICE, "pa", {})])
    await add_game(session_factory, riot_id="EUW1_2", players=[(BOB, "pb", {})])
    async with session_factory() as session:
        duel = await compare(session, GUILD, ALICE, BOB)
    assert duel.left.games == 1
    assert duel.right.games == 1
    assert duel.has_shared_games is False
    assert duel.leader is None


async def test_a_shared_game_is_counted_once_for_each(session_factory):
    await add_game(
        session_factory,
        riot_id="EUW1_1",
        players=[
            (ALICE, "pa", {"score": 70.0, "win": True}),
            (BOB, "pb", {"score": 30.0, "win": True}),
        ],
    )
    async with session_factory() as session:
        duel = await compare(session, GUILD, ALICE, BOB)
    assert duel.together == 1
    assert duel.same_team == 1
    assert duel.against == 0
    assert duel.left_ahead == 1
    assert duel.leader == ALICE


async def test_opposing_teams_are_counted_as_a_real_duel(session_factory):
    await add_game(
        session_factory,
        riot_id="EUW1_1",
        players=[
            (ALICE, "pa", {"win": True, "score": 60.0}),
            (BOB, "pb", {"win": False, "score": 50.0}),
        ],
        teams={ALICE: 100, BOB: 200},
    )
    async with session_factory() as session:
        duel = await compare(session, GUILD, ALICE, BOB)
    assert duel.against == 1
    assert duel.same_team == 0
    assert duel.left_wins_against == 1
    assert duel.right_wins_against == 0


async def test_the_duel_is_symmetric(session_factory):
    await add_game(
        session_factory,
        riot_id="EUW1_1",
        players=[
            (ALICE, "pa", {"score": 70.0}),
            (BOB, "pb", {"score": 30.0}),
        ],
    )
    async with session_factory() as session:
        one = await compare(session, GUILD, ALICE, BOB)
        other = await compare(session, GUILD, BOB, ALICE)
    assert one.leader == other.leader == ALICE
    assert one.left_ahead == other.right_ahead
