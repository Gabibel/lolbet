"""Vannes sur les victoires, et GIF sur les situations qui le méritent.

Deux règles :

* le lot de victoire ne parle que de la victoire, jamais des statistiques,
  pour rester vrai sur un MVP comme sur un joueur porté ;
* un seul GIF par récap, et seulement pour quelques situations — un GIF à
  chaque partie deviendrait du bruit.
"""

from __future__ import annotations

import random
import re

import httpx
import pytest
import respx

from lolbet.services.gif_lines import CAPTIONS, GIFS, TENOR_QUERIES, total_gifs
from lolbet.services.gifs import (
    CATEGORY_TO_SITUATION,
    GifPicker,
    caption_for,
    priority_of,
    situation_for,
)
from lolbet.services.history import PlayerForm
from lolbet.services.scoring import MatchScores
from lolbet.services.taunt_lines import GENERIC_WIN, TAUNTS
from lolbet.services.taunts import (
    GENERIC_WIN_SHARE,
    WIN_POOL_CATEGORIES,
    _draw,
    gif_target,
    taunt_for,
)

from test_taunt_situations import VETERAN, score

# -- victoires -------------------------------------------------------------


def test_the_win_pool_is_substantial():
    assert len(GENERIC_WIN) >= 30


def test_no_win_line_claims_a_statistic():
    """« Porté » ou « 12 morts » serait faux sur un MVP : interdit ici."""
    forbidden = re.compile(
        r"\{|\bport[ée]\b|\bfeed|\bmorts?\b|\bkills?\b|\bKDA\b|\bCS\b|pire joueur",
        re.I,
    )
    offenders = [line for line in GENERIC_WIN if forbidden.search(line)]
    assert offenders == []


def test_every_win_category_can_draw_from_the_pool():
    rng = random.Random(0)
    for category in WIN_POOL_CATEGORIES:
        assert category in TAUNTS
        drawn = {_draw(category, rng) for _ in range(300)}
        assert drawn & set(GENERIC_WIN), category


def test_the_win_pool_never_leaks_into_a_loss():
    rng = random.Random(0)
    for category in ("bad_lost", "fed_lost", "worst_lost", "mvp_lost", "good_lost"):
        drawn = {_draw(category, rng) for _ in range(300)}
        assert not (drawn & set(GENERIC_WIN)), category


def test_a_clean_win_gets_mocked_most_of_the_time():
    """C'est la demande : « vanne même s'il gagne »."""
    lines = [
        taunt_for(
            score(win=True, kills=12, deaths=2, assists=10),
            is_mvp=False,
            is_worst=False,
            duration_seconds=1800,
            form=VETERAN,
            seed=str(seed),
        )
        for seed in range(200)
    ]
    from_pool = sum(line in set(GENERIC_WIN) for line in lines)
    assert abs(from_pool / len(lines) - GENERIC_WIN_SHARE) < 0.12


def test_an_mvp_is_still_mocked_but_never_lied_to():
    form = PlayerForm(games=20, wins=15, losses=5, mvp_count=4)
    for seed in range(100):
        line = taunt_for(
            score(win=True, kills=15, deaths=1, assists=9),
            is_mvp=True,
            is_worst=False,
            duration_seconds=1800,
            form=form,
            seed=str(seed),
        )
        assert "port" not in line.lower() or line in set(TAUNTS["mvp_won"])


# -- GIF : données ---------------------------------------------------------


def test_every_situation_has_gifs_and_captions():
    assert total_gifs() >= 20
    for situation, urls in GIFS.items():
        assert urls, situation
        assert situation in CAPTIONS, situation
        assert situation in TENOR_QUERIES, situation


def test_every_gif_url_is_a_direct_https_gif():
    for urls in GIFS.values():
        for url in urls:
            assert url.startswith("https://"), url
            assert url.endswith(".gif"), url


def test_every_mapped_category_exists_and_points_at_a_real_situation():
    for category, situation in CATEGORY_TO_SITUATION:
        assert category in TAUNTS, category
        assert situation in GIFS, situation


def test_ordinary_games_send_no_gif():
    """Le cas courant. Un GIF par partie serait du bruit."""
    for category in ("good_won", "mvp_won", "good_lost", "mvp_lost", "stomp_won", "first_game"):
        assert situation_for(category) is None


def test_a_losing_streak_outranks_a_plain_feed():
    assert priority_of("streak_lost") < priority_of("fed_lost")
    assert priority_of("good_won") == len(CATEGORY_TO_SITUATION)


def test_captions_mention_the_player():
    rng = random.Random(0)
    for situation in GIFS:
        assert "<@1>" in caption_for(situation, "<@1>", rng)


# -- GIF : choix ------------------------------------------------------------


def _scores(players) -> MatchScores:
    """Dix joueurs : les suivis, plus des figurants répartis autour.

    Sans figurants, un joueur seul serait à la fois MVP et pire joueur, et
    ces deux titres passent avant tout le reste dans le choix de catégorie.
    """
    from dataclasses import replace

    fillers = [
        replace(score(), puuid=f"figurant-{index}", score=value)
        for index, value in enumerate((20.0, 25.0, 30.0, 35.0, 55.0, 60.0, 65.0, 70.0))
    ]
    everyone = list(players) + fillers
    ordered = sorted(everyone, key=lambda p: p.score, reverse=True)
    return MatchScores(
        players=everyone,
        mvp=ordered[0],
        worst=ordered[-1],
        duration_seconds=1800,
        winning_team_id=100,
        team_kills={100: 10, 200: 10},
    )


def test_no_gif_for_a_normal_game():
    p = score(win=True, kills=8, deaths=3, assists=6)
    assert gif_target(_scores([p]), {"p1": 11}, forms={"p1": VETERAN}) is None


def test_three_losses_in_a_row_earn_the_losing_streak_gif():
    p = score(win=False, kills=4, deaths=5, assists=6)
    form = PlayerForm(games=20, wins=5, losses=15, streak=-2, worst_deaths=20)
    target = gif_target(_scores([p]), {"p1": 11}, forms={"p1": form})
    assert target == (11, "losing_streak")


def test_the_most_notable_player_wins_the_only_gif():
    """Deux joueurs suivis éligibles : la série bat le feed."""
    from dataclasses import replace

    feeder = replace(score(win=False, kills=1, deaths=12, assists=2), puuid="feeder", score=5.0)
    streaker = replace(score(win=False, kills=4, deaths=5, assists=6), puuid="streaker", score=40.0)
    forms = {
        "feeder": PlayerForm(games=20, wins=10, losses=10, worst_deaths=20),
        "streaker": PlayerForm(games=20, wins=5, losses=15, streak=-3, worst_deaths=20),
    }
    target = gif_target(
        _scores([feeder, streaker]), {"feeder": 1, "streaker": 2}, forms=forms
    )
    assert target == (2, "losing_streak")


def test_winning_badly_is_a_lucky_win():
    from dataclasses import replace

    p = replace(score(win=True, kills=1, deaths=11, assists=2), score=5.0)
    form = PlayerForm(games=20, wins=10, losses=10, worst_deaths=20)
    target = gif_target(_scores([p]), {"p1": 11}, forms={"p1": form})
    assert target == (11, "lucky_win")


# -- GIF : sources ----------------------------------------------------------


async def test_without_a_key_only_the_curated_list_is_used():
    picker = GifPicker(None)
    try:
        assert picker.uses_tenor is False
        url = await picker.pick("losing_streak", random.Random(0))
    finally:
        await picker.aclose()
    assert url in GIFS["losing_streak"]


async def test_an_unknown_situation_yields_nothing():
    picker = GifPicker(None)
    try:
        assert await picker.pick("nope", random.Random(0)) is None
    finally:
        await picker.aclose()


@respx.mock
async def test_tenor_results_join_the_pool_and_are_cached():
    route = respx.get("https://tenor.googleapis.com/v2/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"media_formats": {"gif": {"url": "https://media.tenor.com/x/a.gif"}}},
                    {"media_formats": {"gif": {"url": "https://media.tenor.com/x/b.gif"}}},
                ]
            },
        )
    )
    picker = GifPicker("clef")
    try:
        seen = set()
        for seed in range(60):
            seen.add(await picker.pick("worst", random.Random(seed)))
    finally:
        await picker.aclose()
    assert "https://media.tenor.com/x/a.gif" in seen
    assert seen & set(GIFS["worst"]), "la liste curée doit rester dans le tirage"
    assert route.call_count == 1  # une requête par situation et par heure


@respx.mock
async def test_a_tenor_outage_falls_back_to_the_curated_list():
    route = respx.get("https://tenor.googleapis.com/v2/search").mock(
        return_value=httpx.Response(503)
    )
    picker = GifPicker("clef")
    try:
        first = await picker.pick("fed", random.Random(1))
        second = await picker.pick("fed", random.Random(2))
    finally:
        await picker.aclose()
    assert first in GIFS["fed"] and second in GIFS["fed"]
    assert route.call_count == 1  # l'échec est mémorisé, pas martelé


@pytest.mark.parametrize("situation", sorted(GIFS))
def test_every_situation_is_reachable_from_some_category(situation):
    assert situation in {s for _, s in CATEGORY_TO_SITUATION}
