"""Suivi de rang Overwatch.

Deux règles portent tout le module :

* le rang n'est fait que d'une division et d'un palier, donc on compare des
  positions, jamais des points — le jeu n'en publie aucun ;
* le tout premier relevé d'un compte n'est pas un changement. Le bot découvre
  le rang, il ne le voit pas bouger, et l'annoncer serait faux.
"""

from __future__ import annotations

import pytest

from lolbet.overwatch.client import (
    InvalidBattleTag,
    normalise_battletag,
    to_player_id,
)
from lolbet.overwatch.rank import (
    DIVISIONS,
    OwRank,
    busiest_platform,
    parse_summary,
    score_to_label,
    season_of,
)
from lolbet.services.ow_taunt_lines import OW_TAUNTS
from lolbet.services.ow_taunts import ow_taunt_content, ow_taunt_for
from lolbet.services.overwatch import (
    RoleChange,
    apply_ranks,
    latest_ow_ranks,
    latest_ow_snapshot,
    peak_rank,
    record_ow_snapshot,
)

TAG = "Joueur#1234"


def summary(pc: dict | None = None, console: dict | None = None, season: int = 22) -> dict:
    def container(roles: dict | None) -> dict | None:
        if roles is None:
            return None
        base = {"season": season, "tank": None, "damage": None, "support": None, "open": None}
        base.update(roles)
        return base

    return {
        "username": "Joueur",
        "avatar": "https://example.invalid/a.png",
        "competitive": {"pc": container(pc), "console": container(console)},
    }


def role(division: str, tier: int) -> dict:
    return {"division": division, "tier": tier}


# -- BattleTag -------------------------------------------------------------


def test_a_battletag_is_normalised_to_one_shape():
    assert normalise_battletag(" TeKrop#2217 ") == "TeKrop#2217"
    assert normalise_battletag("TeKrop-2217") == "TeKrop#2217"


def test_the_url_form_uses_a_dash():
    assert to_player_id("TeKrop#2217") == "TeKrop-2217"


@pytest.mark.parametrize(
    "value", ["TeKrop", "a#12", "TeKrop#abcd", "", "Te Krop#1234", "#1234"]
)
def test_a_malformed_battletag_is_refused(value):
    """Saisi à la main, donc régulièrement faux : mieux vaut le dire tout de suite."""
    with pytest.raises(InvalidBattleTag):
        normalise_battletag(value)


# -- échelle ---------------------------------------------------------------


def test_tier_five_is_the_bottom_of_a_division():
    """Contre-intuitif, et faux dans l'autre sens : 1 est le meilleur palier."""
    assert OwRank("tank", "gold", 5).score < OwRank("tank", "gold", 1).score


def test_the_top_of_a_division_is_just_below_the_next_one():
    assert OwRank("tank", "gold", 1).score + 1 == OwRank("tank", "platinum", 5).score


def test_the_ladder_runs_from_bronze_to_ultimate():
    assert OwRank("tank", "bronze", 5).score == 0
    assert OwRank("tank", "ultimate", 1).score == len(DIVISIONS) * 5 - 1


def test_champion_is_read_as_ultimate():
    """Blizzard a renommé le sommet : un vieux relevé reste comparable."""
    from lolbet.overwatch.rank import normalise_division

    assert normalise_division("champion") == "ultimate"
    assert OwRank("tank", normalise_division("champion"), 1).known


def test_an_unknown_division_scores_zero_rather_than_guessing():
    unknown = OwRank("tank", "mythique", 1)
    assert unknown.known is False
    assert unknown.score == 0


def test_the_label_reads_like_the_game():
    assert OwRank("damage", "gold", 3).label.endswith("Or 3")
    assert "DPS" in OwRank("damage", "gold", 3).display


def test_score_to_label_is_the_inverse():
    for division in DIVISIONS:
        for tier in (1, 3, 5):
            rank = OwRank("tank", division, tier)
            assert score_to_label(rank.score).endswith(f"{rank.division_label} {tier}")


# -- lecture du résumé -----------------------------------------------------


def test_only_the_roles_actually_played_are_returned():
    """Un rôle non classé n'est pas un rang à zéro : il est absent."""
    ranks = parse_summary(summary(pc={"support": role("silver", 4)}))
    assert set(ranks) == {"support"}
    assert ranks["support"].tier == 4


def test_every_role_is_read_including_open_queue():
    ranks = parse_summary(
        summary(
            pc={
                "tank": role("gold", 1),
                "damage": role("platinum", 5),
                "support": role("diamond", 3),
                "open": role("bronze", 2),
            }
        )
    )
    assert set(ranks) == {"tank", "damage", "support", "open"}


def test_a_player_without_any_competitive_data_reads_empty():
    assert parse_summary(summary()) == {}
    assert parse_summary({}) == {}


def test_the_platform_is_honoured():
    payload = summary(pc={"tank": role("gold", 1)}, console={"damage": role("bronze", 2)})
    assert set(parse_summary(payload, "pc")) == {"tank"}
    assert set(parse_summary(payload, "console")) == {"damage"}


def test_the_busiest_platform_prefers_pc_but_falls_back():
    assert busiest_platform(summary(pc={"tank": role("gold", 1)})) == "pc"
    assert busiest_platform(summary(console={"tank": role("gold", 1)})) == "console"
    assert busiest_platform(summary()) == "pc"


def test_a_zero_season_is_not_reported():
    """Blizzard renvoie parfois 0, ce qui ne veut rien dire."""
    assert season_of(summary(pc={"tank": role("gold", 1)}, season=0)) is None
    assert season_of(summary(pc={"tank": role("gold", 1)}, season=22)) == 22


# -- relevés ---------------------------------------------------------------


async def test_a_snapshot_is_written_once(session_factory):
    rank = OwRank("tank", "gold", 3)
    async with session_factory() as session:
        first = await record_ow_snapshot(
            session, battletag=TAG, platform="pc", rank=rank
        )
        await session.commit()
    assert first is not None

    async with session_factory() as session:
        again = await record_ow_snapshot(
            session, battletag=TAG, platform="pc", rank=rank
        )
        await session.commit()
    assert again is None  # rien n'a bouge, rien n'est ecrit


async def test_a_changed_tier_is_written(session_factory):
    async with session_factory() as session:
        await record_ow_snapshot(
            session, battletag=TAG, platform="pc", rank=OwRank("tank", "gold", 3)
        )
        await session.commit()
    async with session_factory() as session:
        second = await record_ow_snapshot(
            session, battletag=TAG, platform="pc", rank=OwRank("tank", "gold", 2)
        )
        await session.commit()
    assert second is not None
    assert second.tier == 2


async def test_the_two_platforms_never_share_a_snapshot(session_factory):
    async with session_factory() as session:
        await record_ow_snapshot(
            session, battletag=TAG, platform="pc", rank=OwRank("tank", "gold", 3)
        )
        await record_ow_snapshot(
            session, battletag=TAG, platform="console", rank=OwRank("tank", "bronze", 1)
        )
        await session.commit()

    async with session_factory() as session:
        on_pc = await latest_ow_snapshot(session, TAG, "tank", "pc")
        on_console = await latest_ow_snapshot(session, TAG, "tank", "console")
    assert on_pc.division == "gold"
    assert on_console.division == "bronze"


# -- ce qui est annoncé ----------------------------------------------------


async def test_the_first_reading_is_never_announced(session_factory):
    """Le bot découvre le rang, il ne le voit pas monter."""
    async with session_factory() as session:
        changes = await apply_ranks(
            session,
            battletag=TAG,
            platform="pc",
            ranks={"tank": OwRank("tank", "gold", 3)},
        )
        await session.commit()
    assert changes == []

    # Mais le relevé est bien enregistré : c'est la référence.
    async with session_factory() as session:
        assert await latest_ow_snapshot(session, TAG, "tank", "pc") is not None


async def test_the_second_reading_reports_what_moved(session_factory):
    async with session_factory() as session:
        await apply_ranks(
            session,
            battletag=TAG,
            platform="pc",
            ranks={"tank": OwRank("tank", "gold", 3), "damage": OwRank("damage", "silver", 2)},
        )
        await session.commit()

    async with session_factory() as session:
        changes = await apply_ranks(
            session,
            battletag=TAG,
            platform="pc",
            ranks={
                "tank": OwRank("tank", "gold", 2),  # a bougé
                "damage": OwRank("damage", "silver", 2),  # inchangé
            },
        )
        await session.commit()

    assert [change.role for change in changes] == ["tank"]
    assert changes[0].category == "tier_up"
    assert changes[0].steps == 1


async def test_a_role_appearing_later_is_a_placement(session_factory):
    async with session_factory() as session:
        await apply_ranks(
            session, battletag=TAG, platform="pc", ranks={"tank": OwRank("tank", "gold", 3)}
        )
        await session.commit()

    async with session_factory() as session:
        changes = await apply_ranks(
            session,
            battletag=TAG,
            platform="pc",
            ranks={
                "tank": OwRank("tank", "gold", 3),
                "support": OwRank("support", "bronze", 5),
            },
        )
        await session.commit()

    assert [change.category for change in changes] == ["placed"]
    assert changes[0].is_placement


async def test_a_role_that_disappears_is_left_alone(session_factory):
    """Un rôle absent du résumé n'est pas une chute : c'est une absence."""
    async with session_factory() as session:
        await apply_ranks(
            session,
            battletag=TAG,
            platform="pc",
            ranks={"tank": OwRank("tank", "gold", 3), "damage": OwRank("damage", "gold", 3)},
        )
        await session.commit()

    async with session_factory() as session:
        changes = await apply_ranks(
            session, battletag=TAG, platform="pc", ranks={"tank": OwRank("tank", "gold", 3)}
        )
        await session.commit()

    assert changes == []
    async with session_factory() as session:
        ranks = await latest_ow_ranks(session, TAG, "pc")
    assert "damage" in ranks  # le dernier rang connu reste consultable


async def test_the_peak_is_the_best_ever_seen(session_factory):
    async with session_factory() as session:
        for division, tier in (("gold", 3), ("platinum", 5), ("silver", 1)):
            await record_ow_snapshot(
                session,
                battletag=TAG,
                platform="pc",
                rank=OwRank("tank", division, tier),
            )
        await session.commit()

    async with session_factory() as session:
        best = await peak_rank(session, TAG, "tank", "pc")
        current = await latest_ow_snapshot(session, TAG, "tank", "pc")
    assert best.division == "platinum"
    assert current.division == "silver"


# -- catégories ------------------------------------------------------------


def change(before: tuple[str, int] | None, after: tuple[str, int]) -> RoleChange:
    previous = OwRank("tank", *before) if before else None
    return RoleChange(role="tank", current=OwRank("tank", *after), previous=previous)


def test_crossing_a_division_outranks_a_plain_tier_move():
    assert change(("gold", 1), ("platinum", 5)).category == "promoted"
    assert change(("platinum", 5), ("gold", 1)).category == "demoted"
    assert change(("gold", 3), ("gold", 2)).category == "tier_up"
    assert change(("gold", 2), ("gold", 3)).category == "tier_down"
    assert change(None, ("gold", 2)).category == "placed"


def test_a_placement_has_no_delta_to_report():
    placed = change(None, ("gold", 2))
    assert placed.steps == 0
    assert placed.direction == 0
    assert "nouveau" in placed.line


def test_the_line_shows_both_ends_of_the_move():
    line = change(("gold", 3), ("gold", 2)).line
    assert "Or 3" in line and "Or 2" in line


# -- phrases ---------------------------------------------------------------


def test_every_category_has_lines():
    assert set(OW_TAUNTS) == {"promoted", "demoted", "tier_up", "tier_down", "placed"}
    assert all(len(lines) >= 10 for lines in OW_TAUNTS.values())


def test_every_line_uses_only_known_fields():
    sample = {"role": "DPS", "rank": "Or 3", "previous": "Or 4", "steps": "1 cran"}
    for name, lines in OW_TAUNTS.items():
        for line in lines:
            try:
                line.format(**sample)
            except (KeyError, IndexError, ValueError) as exc:  # pragma: no cover
                pytest.fail(f"{name}: {line!r} -> {exc}")


def test_a_taunt_renders_without_leftover_placeholders():
    for seed in range(40):
        for before, after in ((("gold", 3), ("gold", 2)), (("gold", 1), ("platinum", 5))):
            line = ow_taunt_for(change(before, after), seed=str(seed))
            assert "{" not in line and "}" not in line


def test_the_same_change_always_gets_the_same_line():
    """Un ré-affichage ne doit pas faire muter la phrase."""
    first = ow_taunt_for(change(("gold", 3), ("gold", 2)), seed="abc")
    second = ow_taunt_for(change(("gold", 3), ("gold", 2)), seed="abc")
    assert first == second


def test_one_line_per_role_that_moved():
    content = ow_taunt_content(
        [
            RoleChange("tank", OwRank("tank", "gold", 2), OwRank("tank", "gold", 3)),
            RoleChange("damage", OwRank("damage", "silver", 4), OwRank("damage", "silver", 3)),
        ],
        seed="x",
    )
    assert len(content.splitlines()) == 2


def test_a_placement_line_never_mentions_a_previous_rank():
    """``{previous}`` est vide sur un placement : aucune phrase ne doit l'utiliser."""
    for line in OW_TAUNTS["placed"]:
        assert "{previous}" not in line
