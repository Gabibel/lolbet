"""Historique des parties, forme du joueur et vannes à mémoire."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lolbet.models import GameStatus, PlayerGameStat, TrackedGame, TrackedParticipant
from lolbet.services.history import (
    PlayerForm,
    guild_recent_games,
    player_form,
    record_game_stats,
    recent_games,
)
from lolbet.services.scoring import score_match
from lolbet.services.taunts import TAUNTS, _category, build_taunt_content, taunt_for
from lolbet.utils import utcnow

GUILD = 777
ALICE, BOB = 11, 22
POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def participant_dict(puuid: str, index: int, *, win: bool, deaths: int = 3, kills: int = 5):
    return {
        "puuid": puuid,
        "riotIdGameName": puuid,
        "riotIdTagline": "EUW",
        "championId": 64,
        "championName": "LeeSin",
        "teamId": 100 if win else 200,
        "teamPosition": POSITIONS[index % 5],
        "win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": 5,
        "totalDamageDealtToChampions": 20000,
        "goldEarned": 12000,
        "totalMinionsKilled": 180,
        "neutralMinionsKilled": 0,
        "visionScore": 20,
        "totalDamageTaken": 20000,
        "damageSelfMitigated": 15000,
    }


def build_scores(*, alice_wins: bool, alice_deaths: int = 3):
    parts = [participant_dict("alice", 0, win=alice_wins, deaths=alice_deaths)]
    for i in range(1, 10):
        parts.append(participant_dict(f"p{i}", i, win=(i % 2 == 0)))
    return score_match(
        {
            "info": {
                "gameDuration": 1800,
                "gameEndTimestamp": 1,
                "participants": parts,
                "teams": [
                    {"teamId": 100, "win": alice_wins},
                    {"teamId": 200, "win": not alice_wins},
                ],
            }
        }
    )


async def make_resolved_game(session_factory, number: int) -> tuple[TrackedGame, list]:
    async with session_factory() as session:
        game = TrackedGame(
            guild_id=GUILD,
            riot_game_id=f"EUW1_{number}",
            platform="euw1",
            queue_id=420,
            status=GameStatus.RESOLVED,
            tracked_team_id=100,
        )
        session.add(game)
        await session.flush()
        participant = TrackedParticipant(
            game_id=int(game.id or 0),
            puuid="alice",
            discord_id=ALICE,
            riot_id="Alice#EUW",
            team_id=100,
        )
        session.add(participant)
        await session.commit()
        return game, [participant]


async def play(session_factory, number: int, *, win: bool, deaths: int = 3):
    game, participants = await make_resolved_game(session_factory, number)
    scores = build_scores(alice_wins=win, alice_deaths=deaths)
    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        created = await record_game_stats(session, stored, scores, participants)
        # Ordonner les parties dans le temps, sinon elles partagent l'instant.
        for stat in created:
            stat.played_at = utcnow() + timedelta(seconds=number)
            session.add(stat)
        await session.commit()
    return scores


# -- enregistrement --------------------------------------------------------


async def test_stats_are_recorded_for_tracked_players(session_factory):
    await play(session_factory, 1, win=True)
    async with session_factory() as session:
        rows = await recent_games(session, GUILD, ALICE)
    assert len(rows) == 1
    assert rows[0].win is True
    assert rows[0].riot_game_id == "EUW1_1"
    assert rows[0].champion_name == "LeeSin"


async def test_recording_twice_does_not_duplicate(session_factory):
    game, participants = await make_resolved_game(session_factory, 5)
    scores = build_scores(alice_wins=True)
    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        await record_game_stats(session, stored, scores, participants)
        await session.commit()
    async with session_factory() as session:
        stored = await session.get(TrackedGame, game.id)
        again = await record_game_stats(session, stored, scores, participants)
        await session.commit()
    assert again == []
    async with session_factory() as session:
        assert len(await recent_games(session, GUILD, ALICE)) == 1


async def test_untracked_participants_are_ignored(session_factory):
    """Seuls les inscrits ont une ligne : pas les huit autres joueurs."""
    await play(session_factory, 2, win=True)
    async with session_factory() as session:
        rows = await guild_recent_games(session, GUILD, limit=50)
    assert {r.puuid for r in rows} == {"alice"}


# -- forme -----------------------------------------------------------------


async def test_form_of_a_newcomer_is_empty(session_factory):
    async with session_factory() as session:
        form = await player_form(session, GUILD, ALICE)
    assert form.is_new
    assert form.games == 0


async def test_form_counts_wins_and_losses(session_factory):
    await play(session_factory, 1, win=True)
    await play(session_factory, 2, win=False)
    await play(session_factory, 3, win=True)
    async with session_factory() as session:
        form = await player_form(session, GUILD, ALICE)
    assert form.games == 3
    assert form.wins == 2
    assert form.losses == 1
    assert form.winrate == pytest.approx(200 / 3)


async def test_losing_streak_is_detected(session_factory):
    await play(session_factory, 1, win=True)
    for number in (2, 3, 4):
        await play(session_factory, number, win=False)
    async with session_factory() as session:
        form = await player_form(session, GUILD, ALICE)
    assert form.streak == -3
    assert form.losing_streak == 3
    assert form.winning_streak == 0


async def test_winning_streak_is_detected(session_factory):
    await play(session_factory, 1, win=False)
    for number in (2, 3):
        await play(session_factory, number, win=True)
    async with session_factory() as session:
        form = await player_form(session, GUILD, ALICE)
    assert form.streak == 2
    assert form.winning_streak == 2


async def test_form_remembers_the_worst_game(session_factory):
    await play(session_factory, 1, win=False, deaths=4)
    await play(session_factory, 2, win=False, deaths=13)
    async with session_factory() as session:
        form = await player_form(session, GUILD, ALICE)
    assert form.worst_deaths == 13


async def test_form_is_scoped_to_the_player(session_factory):
    await play(session_factory, 1, win=True)
    async with session_factory() as session:
        other = await player_form(session, GUILD, BOB)
    assert other.is_new


# -- vannes à mémoire ------------------------------------------------------


def score_of(scores, puuid="alice"):
    return scores.by_puuid(puuid)


def test_a_first_game_gets_its_own_category():
    scores = build_scores(alice_wins=False, alice_deaths=12)
    line = taunt_for(
        score_of(scores),
        is_mvp=False,
        is_worst=False,
        duration_seconds=1800,
        form=PlayerForm(),
    )
    assert line in TAUNTS["first_game"]


def test_a_third_defeat_in_a_row_is_called_out():
    scores = build_scores(alice_wins=False, alice_deaths=4)
    form = PlayerForm(games=5, wins=3, losses=2, streak=-2)
    assert (
        _category(score_of(scores), is_mvp=False, is_worst=False, form=form)
        == "streak_lost"
    )
    line = taunt_for(
        score_of(scores), is_mvp=False, is_worst=False, duration_seconds=1800, form=form
    )
    assert "3" in line  # la série inclut la partie qui vient de se jouer


def test_a_streak_that_just_broke_is_not_announced():
    """Gagner après deux défaites ne doit pas parler de série."""
    scores = build_scores(alice_wins=True)
    form = PlayerForm(games=5, wins=3, losses=2, streak=-2)
    assert (
        _category(score_of(scores), is_mvp=False, is_worst=False, form=form)
        != "streak_won"
    )


def test_two_defeats_are_not_yet_a_streak():
    scores = build_scores(alice_wins=False, alice_deaths=4)
    form = PlayerForm(games=3, wins=2, losses=1, streak=-1)
    assert (
        _category(score_of(scores), is_mvp=False, is_worst=False, form=form)
        != "streak_lost"
    )


def test_a_personal_death_record_takes_priority():
    scores = build_scores(alice_wins=False, alice_deaths=14)
    form = PlayerForm(games=10, wins=5, losses=5, streak=-1, worst_deaths=11)
    assert (
        _category(score_of(scores), is_mvp=False, is_worst=False, form=form)
        == "record_deaths"
    )


def test_a_modest_death_count_is_never_a_record():
    """Battre son record avec 4 morts n'a rien de remarquable."""
    scores = build_scores(alice_wins=False, alice_deaths=4)
    form = PlayerForm(games=2, wins=1, losses=1, streak=-1, worst_deaths=2)
    assert (
        _category(score_of(scores), is_mvp=False, is_worst=False, form=form)
        != "record_deaths"
    )


def test_without_form_the_old_behaviour_is_kept():
    scores = build_scores(alice_wins=False, alice_deaths=12)
    assert (
        _category(score_of(scores), is_mvp=False, is_worst=False, form=None)
        == "fed_lost"
    )


def test_streak_number_is_injected():
    scores = build_scores(alice_wins=True)
    form = PlayerForm(games=9, wins=6, losses=3, streak=4)
    line = taunt_for(
        score_of(scores), is_mvp=False, is_worst=False, duration_seconds=1800, form=form
    )
    assert "{streak}" not in line
    assert "5" in line


def test_content_uses_the_forms_it_is_given():
    scores = build_scores(alice_wins=False, alice_deaths=4)
    content = build_taunt_content(
        scores,
        {"alice": 111},
        seed="EUW1_1",
        forms={"alice": PlayerForm(games=4, wins=1, losses=3, streak=-3)},
    )
    assert "<@111>" in content
    assert "4" in content  # quatrième défaite d'affilée
