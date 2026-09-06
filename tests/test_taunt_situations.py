"""Chaque situation doit déclencher sa propre catégorie de vanne.

Le principe testé ici : la vanne retenue est toujours la **plus spécifique**
qui s'applique. Un record bat une série, une série bat une partie banale.
"""

from __future__ import annotations

import pytest

from lolbet.models import RankSnapshot
from lolbet.services.history import PlayerForm
from lolbet.services.progression import RankChange
from lolbet.services.scoring import PlayerScore
from lolbet.services.taunt_lines import TAUNTS, total_lines
from lolbet.services.taunts import _category, taunt_for

VETERAN = PlayerForm(games=20, wins=10, losses=10, streak=1, worst_deaths=8, best_kills=9)


def score(
    *,
    win: bool = False,
    kills: int = 5,
    deaths: int = 3,
    assists: int = 5,
    position: str = "MIDDLE",
) -> PlayerScore:
    return PlayerScore(
        puuid="p1",
        riot_id="Joueur#EUW",
        champion_id=64,
        champion_name="LeeSin",
        team_id=100,
        position=position,
        win=win,
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=180,
        cs_per_min=6.0,
        damage=20_000,
        gold=12_000,
        vision_score=25,
        score=40.0,
        metrics={"damage_share": 0.25},
    )


def snapshot(tier="GOLD", division="IV", lp=50) -> RankSnapshot:
    from lolbet.riot.rank import RankInfo

    info = RankInfo("RANKED_SOLO_5x5", tier, division, lp)
    return RankSnapshot(
        puuid="p1", platform="euw1", tier=tier, division=division,
        league_points=lp, ladder_score=info.score,
    )


def change(before, after) -> RankChange:
    return RankChange(puuid="p1", previous=before, current=after)


def pick(minutes: int = 30, **kwargs) -> str:
    form = kwargs.pop("form", VETERAN)
    is_mvp = kwargs.pop("is_mvp", False)
    is_worst = kwargs.pop("is_worst", False)
    rank_change = kwargs.pop("rank_change", None)
    return _category(
        score(**kwargs),
        is_mvp=is_mvp,
        is_worst=is_worst,
        form=form,
        duration_seconds=minutes * 60,
        rank_change=rank_change,
    )


# -- couverture ------------------------------------------------------------


def test_there_are_hundreds_of_lines():
    assert total_lines() >= 400


def test_no_category_is_left_empty():
    assert len(TAUNTS) == 27
    assert all(len(lines) >= 10 for lines in TAUNTS.values())


def test_every_line_uses_only_known_fields():
    """Un champ inconnu entre accolades ferait planter le formatage."""
    known = {
        "deaths",
        "kills",
        "assists",
        "streak",
        "minutes",
        "cs",
        "cs_per_min",
        "vision",
        "damage",
        "lp",
    }
    sample = dict.fromkeys(known, 1)
    for name, lines in TAUNTS.items():
        for line in lines:
            try:
                line.format(**sample)
            except (KeyError, IndexError, ValueError) as exc:  # pragma: no cover
                pytest.fail(f"{name}: {line!r} -> {exc}")


# -- une situation, une catégorie -----------------------------------------


def test_zero_deaths_is_its_own_situation():
    assert pick(deaths=0, win=True) == "deathless_won"
    assert pick(deaths=0, win=False) == "deathless_lost"


def test_zero_deaths_in_a_remake_is_not_remarkable():
    """Sur 8 minutes, ne pas mourir ne prouve rien."""
    assert pick(minutes=8, deaths=0, win=True) != "deathless_won"


def test_a_short_game_is_a_stomp():
    assert pick(minutes=16, win=True) == "stomp_won"
    assert pick(minutes=16, win=False) == "stomp_lost"


def test_a_long_game_is_a_marathon():
    assert pick(minutes=48, win=True) == "long_game_won"
    assert pick(minutes=48, win=False) == "long_game_lost"


def test_a_normal_length_game_is_judged_on_performance():
    assert pick(minutes=30, kills=12, deaths=2, assists=10, win=True) == "good_won"
    assert pick(minutes=30, kills=1, deaths=9, assists=2, win=False) == "bad_lost"


def test_a_kill_record_is_announced():
    assert pick(kills=17, win=True) == "record_kills"


def test_a_good_game_that_beats_no_record_is_not_announced():
    form = PlayerForm(games=20, wins=10, losses=10, best_kills=25)
    assert pick(kills=17, win=True, form=form) != "record_kills"


def test_a_first_mvp_is_special():
    form = PlayerForm(games=20, wins=10, losses=10, mvp_count=0)
    assert pick(is_mvp=True, win=True, form=form) == "first_mvp"


def test_a_regular_mvp_is_not():
    form = PlayerForm(games=20, wins=10, losses=10, mvp_count=4)
    assert pick(is_mvp=True, win=True, form=form) == "mvp_won"


def test_a_repeat_offender_gets_the_repeat_line():
    form = PlayerForm(games=20, wins=8, losses=12, lvp_count=3)
    assert pick(is_worst=True, win=False, form=form) == "repeat_lvp"


def test_a_first_lvp_is_just_the_worst_line():
    form = PlayerForm(games=20, wins=10, losses=10, lvp_count=0)
    assert pick(is_worst=True, win=False, form=form) == "worst_lost"


# -- ordre de priorité -----------------------------------------------------


def test_a_death_record_beats_a_losing_streak():
    """Un record est plus rare qu'une série : c'est lui qu'on raconte."""
    form = PlayerForm(games=20, wins=5, losses=15, streak=-4, worst_deaths=9)
    assert pick(deaths=13, win=False, form=form) == "record_deaths"


def test_a_streak_beats_the_game_length():
    form = PlayerForm(games=20, wins=5, losses=15, streak=-3, worst_deaths=20)
    assert pick(minutes=50, deaths=4, win=False, form=form) == "streak_lost"


def test_a_title_beats_a_streak():
    form = PlayerForm(games=20, wins=15, losses=5, streak=5, mvp_count=3)
    assert pick(is_mvp=True, win=True, form=form) == "mvp_won"


def test_the_game_length_beats_a_plain_performance():
    form = PlayerForm(games=20, wins=10, losses=10, streak=1, worst_deaths=20)
    assert pick(minutes=52, kills=1, deaths=9, win=False, form=form) == "long_game_lost"


def test_a_newcomer_short_circuits_everything():
    assert pick(deaths=0, win=True, form=PlayerForm()) == "first_game"


def test_without_history_no_category_needs_it():
    """Sans forme, seules les catégories de partie peuvent sortir."""
    needs_history = {
        "first_game",
        "record_deaths",
        "record_kills",
        "streak_lost",
        "streak_won",
        "first_mvp",
        "repeat_lvp",
    }
    for minutes in (10, 30, 50):
        for deaths in (0, 3, 12):
            for win in (True, False):
                category = _category(
                    score(deaths=deaths, win=win),
                    is_mvp=False,
                    is_worst=False,
                    form=None,
                    duration_seconds=minutes * 60,
                )
                assert category not in needs_history


# -- rendu -----------------------------------------------------------------


def test_the_minutes_are_injected_in_length_lines():
    line = taunt_for(
        score(win=False), is_mvp=False, is_worst=False, duration_seconds=52 * 60, form=VETERAN
    )
    assert "52" in line


def test_every_category_renders_without_leftovers():
    """Tirage sur beaucoup de graines : aucune phrase ne doit rester brute."""
    for seed in range(60):
        for minutes, deaths, win in ((16, 0, True), (30, 12, False), (50, 3, True)):
            line = taunt_for(
                score(deaths=deaths, win=win),
                is_mvp=False,
                is_worst=False,
                duration_seconds=minutes * 60,
                seed=str(seed),
                form=VETERAN,
            )
            assert "{" not in line and "}" not in line
            assert line.strip()


# -- les LP ----------------------------------------------------------------


def test_losing_a_division_is_the_headline():
    """Retrograder prime sur tout le reste, meme un record de morts."""
    dropped = change(snapshot("GOLD", "IV", 8), snapshot("SILVER", "I", 75))
    assert pick(deaths=14, win=False, rank_change=dropped) == "demoted"


def test_gaining_a_division_is_the_headline():
    climbed = change(snapshot("SILVER", "I", 92), snapshot("GOLD", "IV", 12))
    assert pick(win=True, rank_change=climbed) == "promoted"


def test_a_big_lp_swing_without_a_division_change():
    crashed = change(snapshot("GOLD", "IV", 60), snapshot("GOLD", "IV", 28))
    assert pick(win=False, rank_change=crashed) == "lp_crash"

    surged = change(snapshot("GOLD", "IV", 20), snapshot("GOLD", "IV", 55))
    assert pick(win=True, rank_change=surged) == "lp_surge"


def test_a_small_lp_swing_is_not_worth_mentioning():
    tiny = change(snapshot("GOLD", "IV", 50), snapshot("GOLD", "IV", 62))
    assert pick(win=True, rank_change=tiny) not in {"lp_surge", "lp_crash", "promoted"}


def test_a_first_snapshot_has_nothing_to_compare():
    """Sans releve precedent, on ne peut rien dire des LP."""
    first = change(None, snapshot("GOLD", "IV", 50))
    assert first.known is False
    assert pick(win=True, rank_change=first) not in {"promoted", "demoted", "lp_surge"}


def test_the_lp_amount_is_injected_without_a_sign():
    crashed = change(snapshot("GOLD", "IV", 60), snapshot("GOLD", "IV", 28))
    line = taunt_for(
        score(win=False), is_mvp=False, is_worst=False,
        duration_seconds=1800, form=VETERAN, rank_change=crashed, seed="s",
    )
    assert "32" in line
    assert "-32" not in line  # la phrase porte deja le sens de la perte


def test_rank_change_reports_its_direction():
    assert change(snapshot("GOLD", "IV", 8), snapshot("SILVER", "I", 75)).direction == -1
    assert change(snapshot("SILVER", "I", 92), snapshot("GOLD", "IV", 12)).direction == 1
    assert change(snapshot("GOLD", "IV", 20), snapshot("GOLD", "IV", 55)).direction == 0


def test_signed_delta_reads_correctly():
    assert change(snapshot("GOLD", "IV", 20), snapshot("GOLD", "IV", 55)).signed_delta == "+35 LP"
    assert change(snapshot("GOLD", "IV", 55), snapshot("GOLD", "IV", 20)).signed_delta == "-35 LP"
    assert change(None, snapshot()).signed_delta == "LP inconnus"


def test_an_unchanged_rank_is_not_a_measured_delta():
    """Riot n'a pas encore applique les LP : ne rien inventer."""
    same = snapshot("GOLD", "IV", 75)
    stalled = RankChange(puuid="p1", previous=same, current=same, moved=False)
    assert stalled.known is False
    assert stalled.signed_delta == "LP inconnus"
    assert pick(win=True, rank_change=stalled) not in {"promoted", "lp_surge"}


def test_a_measured_delta_is_reported():
    moved = RankChange(
        puuid="p1",
        previous=snapshot("GOLD", "IV", 40),
        current=snapshot("GOLD", "IV", 75),
        moved=True,
    )
    assert moved.known is True
    assert moved.signed_delta == "+35 LP"


def test_the_recap_label_drops_the_win_loss_record():
    """La ligne du recap est deja dense : pas de bilan en plus."""
    change_ = RankChange(puuid="p1", previous=None, current=snapshot("GOLD", "IV", 75))
    assert "75 LP" in change_.label
    assert "%" not in change_.label
