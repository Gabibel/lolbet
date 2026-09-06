"""Les vannes de fin de partie."""

from __future__ import annotations

from lolbet.services.scoring import MatchScores, PlayerScore
from lolbet.services.taunt_lines import LVP_LINES, MVP_LINES
from lolbet.services.taunts import TAUNTS, build_taunt_content, taunt_for

# Toutes les variantes portent le meme emblene : c'est le marqueur stable,
# la formulation, elle, doit pouvoir etre editee librement.
LVP_MARK = "\N{POLICE CAR}"
MVP_MARK = "\N{GLOWING STAR}"


def score(
    *,
    puuid: str = "p1",
    win: bool = False,
    kills: int = 3,
    deaths: int = 3,
    assists: int = 5,
    vision: int = 25,
    cs_per_min: float = 6.0,
    position: str = "MIDDLE",
    damage_share: float = 0.25,
) -> PlayerScore:
    return PlayerScore(
        puuid=puuid,
        riot_id=f"{puuid}#EUW",
        champion_id=64,
        champion_name="LeeSin",
        team_id=100,
        position=position,
        win=win,
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=int(cs_per_min * 30),
        cs_per_min=cs_per_min,
        damage=20_000,
        gold=12_000,
        vision_score=vision,
        score=40.0,
        metrics={"damage_share": damage_share},
    )


def scores_for(players: list[PlayerScore], mvp=None, worst=None) -> MatchScores:
    return MatchScores(
        players=players,
        mvp=mvp,
        worst=worst,
        duration_seconds=1800,
        winning_team_id=100,
        team_kills={100: 20, 200: 15},
    )


def test_every_category_has_lines():
    assert all(lines for lines in TAUNTS.values())


def test_special_lines_all_carry_their_mark():
    """Les tests, comme les joueurs, reperent la ligne a son emblene."""
    assert all(LVP_MARK in line for line in LVP_LINES)
    assert all(MVP_MARK in line for line in MVP_LINES)
    assert all("{mention}" in line for line in LVP_LINES + MVP_LINES)


def test_the_same_match_always_gives_the_same_line():
    """Un récapitulatif réaffiché ne doit pas changer de vanne."""
    player = score(deaths=12)
    first = taunt_for(player, is_mvp=False, is_worst=False, duration_seconds=1800, seed="EUW1_1")
    second = taunt_for(player, is_mvp=False, is_worst=False, duration_seconds=1800, seed="EUW1_1")
    assert first == second


def test_different_players_can_get_different_lines():
    seeds = {
        taunt_for(
            score(puuid=f"p{i}", deaths=12),
            is_mvp=False,
            is_worst=False,
            duration_seconds=1800,
            seed="EUW1_1",
        )
        for i in range(12)
    }
    assert len(seeds) > 1


def test_worst_player_who_lost_gets_the_harshest_category():
    line = taunt_for(
        score(deaths=11, win=False), is_mvp=False, is_worst=True, duration_seconds=1800
    )
    assert any(line.startswith(base.split("{")[0]) for base in TAUNTS["worst_lost"])


def test_worst_player_who_won_is_told_he_was_carried():
    line = taunt_for(
        score(deaths=11, win=True), is_mvp=False, is_worst=True, duration_seconds=1800
    )
    assert any(line.startswith(base.split("{")[0]) for base in TAUNTS["worst_won"])


def test_mvp_is_never_piled_on():
    """Un MVP ne reçoit jamais de pique statistique en plus."""
    line = taunt_for(
        score(win=True, kills=15, deaths=1, vision=2, cs_per_min=1.0),
        is_mvp=True,
        is_worst=False,
        duration_seconds=1800,
    )
    assert line in TAUNTS["mvp_won"]


def test_no_placeholder_survives_formatting():
    """Une accolade oubliee dans une phrase se verrait tout de suite."""
    for deaths in (0, 4, 14):
        line = taunt_for(
            score(deaths=deaths), is_mvp=False, is_worst=False, duration_seconds=1800
        )
        assert "{" not in line
        assert "}" not in line


def test_a_support_is_never_mocked_for_his_farm():
    line = taunt_for(
        score(position="UTILITY", cs_per_min=0.8, deaths=12, vision=60),
        is_mvp=False,
        is_worst=False,
        duration_seconds=1800,
    )
    assert "CS par minute" not in line


def test_a_midlaner_with_no_farm_is_mocked_for_it():
    lines = {
        taunt_for(
            score(puuid=f"p{i}", position="MIDDLE", cs_per_min=1.2, deaths=12, vision=40),
            is_mvp=False,
            is_worst=False,
            duration_seconds=1800,
            seed=f"s{i}",
        )
        for i in range(20)
    }
    assert any("CS par minute" in line for line in lines)


def test_short_games_get_no_statistical_jab():
    """Sur une partie de 10 minutes, reprocher le farm n'a aucun sens."""
    line = taunt_for(
        score(cs_per_min=0.5, deaths=12, vision=1),
        is_mvp=False,
        is_worst=False,
        duration_seconds=600,
    )
    assert "vision" not in line.lower()
    assert "CS par minute" not in line


def test_content_mentions_every_tracked_player():
    a, b = score(puuid="a", win=True), score(puuid="b", win=True)
    content = build_taunt_content(scores_for([a, b]), {"a": 111, "b": 222})
    assert "<@111>" in content
    assert "<@222>" in content


def test_lvp_line_only_when_a_tracked_player_is_the_worst():
    tracked = score(puuid="a")
    stranger = score(puuid="z")

    with_lvp = build_taunt_content(scores_for([tracked, stranger], worst=tracked), {"a": 111})
    without = build_taunt_content(scores_for([tracked, stranger], worst=stranger), {"a": 111})

    assert LVP_MARK in with_lvp
    assert "<@111>" in with_lvp
    assert LVP_MARK not in without


def test_mvp_line_when_a_tracked_player_carried():
    tracked = score(puuid="a", win=True, kills=18, deaths=1)
    content = build_taunt_content(scores_for([tracked], mvp=tracked), {"a": 111})
    assert MVP_MARK in content


def test_untracked_players_are_never_targeted():
    """Seuls les inscrits volontaires sont chambrés."""
    tracked = score(puuid="a")
    stranger = score(puuid="z", deaths=20)
    content = build_taunt_content(scores_for([tracked, stranger]), {"a": 111})
    assert "<@111>" in content
    assert "z#EUW" not in content


def test_content_stays_inside_the_discord_limit():
    players = [score(puuid=f"p{i}", deaths=15) for i in range(20)]
    tracked = {f"p{i}": 1000 + i for i in range(20)}
    content = build_taunt_content(scores_for(players), tracked)
    assert len(content) <= 2000


def test_a_player_missing_from_the_match_is_skipped():
    content = build_taunt_content(scores_for([score(puuid="a")]), {"absent": 999})
    assert content == ""
