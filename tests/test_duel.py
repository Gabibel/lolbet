"""Parties où plusieurs inscrits jouent ensemble ou l'un contre l'autre."""

from __future__ import annotations

from dataclasses import dataclass

from lolbet.models import BetSide
from lolbet.services.betting import Pool, Settlement
from lolbet.services.embeds import (
    SideLabels,
    build_lock_embed,
    build_result_embed,
    side_labels_for,
)
from lolbet.services.enrichment import base_card, find_team_id
from lolbet.views import bet_panel_text


@dataclass
class Tracked:
    """Ce que side_labels_for attend : un camp et un Riot ID."""

    team_id: int
    riot_id: str


class FakeDDragon:
    def champion_name(self, champion_id: int) -> str:
        return f"Champion {champion_id}"

    def champion_icon_url(self, champion_id: int) -> str | None:
        return None


def spectator(tracked_teams: dict[str, int]) -> dict:
    return {
        "gameId": 7123456789,
        "gameQueueConfigId": 420,
        "gameStartTime": 1_700_000_000_000,
        "participants": [
            {
                "puuid": f"p{i}",
                "teamId": 100 if i < 5 else 200,
                "championId": 64,
                "riotId": f"Joueur{i}#EUW",
            }
            for i in range(10)
        ],
    }


# -- libellés des deux camps ----------------------------------------------


def test_a_single_tracked_player_keeps_the_plain_labels():
    labels = side_labels_for([Tracked(100, "Gabite#EUW")], 100)
    assert labels.duel is False
    assert labels.win == "VICTOIRE"
    assert labels.loss == "DÉFAITE"


def test_several_tracked_players_on_the_same_team_is_not_a_duel():
    """Un stack de trois parie toujours sur sa propre victoire."""
    labels = side_labels_for(
        [Tracked(100, "A#EUW"), Tracked(100, "B#EUW"), Tracked(100, "C#EUW")], 100
    )
    assert labels.duel is False
    assert labels.win == "VICTOIRE"


def test_tracked_players_on_both_teams_name_the_two_camps():
    """Parier « défaite » n'a aucun sens quand un inscrit est en face."""
    labels = side_labels_for([Tracked(100, "Gabite#EUW"), Tracked(200, "Mephisto#666")], 100)
    assert labels.duel is True
    assert labels.win == "Gabite"
    assert labels.loss == "Mephisto"


def test_camps_are_grouped_by_team():
    labels = side_labels_for(
        [
            Tracked(100, "A#EUW"),
            Tracked(100, "B#EUW"),
            Tracked(200, "C#EUW"),
        ],
        100,
    )
    assert labels.win == "A, B"
    assert labels.loss == "C"


def test_labels_follow_the_reference_team():
    """Vu depuis l'équipe rouge, les camps sont inversés."""
    tracked = [Tracked(100, "Bleu#EUW"), Tracked(200, "Rouge#EUW")]
    assert side_labels_for(tracked, 200).win == "Rouge"
    assert side_labels_for(tracked, 200).loss == "Bleu"


def test_labels_are_truncated_for_discord_button_limits():
    long_names = [Tracked(100, f"NomTresLong{i}#EUW") for i in range(5)]
    labels = side_labels_for([*long_names, Tracked(200, "Adversaire#EUW")], 100)
    assert len(labels.win) <= 70


def test_side_lookup_falls_back_gracefully():
    labels = SideLabels()
    assert labels.of(BetSide.WIN) == "VICTOIRE"
    assert labels.of(BetSide.LOSS) == "DÉFAITE"
    assert labels.of(None) == "None"


# -- une seule annonce pour toute la partie --------------------------------


def test_one_card_lists_every_tracked_player_of_the_game():
    card = base_card(
        spectator({}),
        platform="euw1",
        riot_game_id="EUW1_1",
        tracked={"p1": 111, "p3": 333, "p7": 777},
    )
    assert len(card.tracked) == 3
    assert {p.discord_id for p in card.tracked} == {111, 333, 777}


def test_a_duel_card_reports_the_duel():
    card = base_card(
        spectator({}), platform="euw1", riot_game_id="EUW1_1", tracked={"p1": 111, "p7": 777}
    )
    card.tracked_team_id = find_team_id(spectator({}), {"p1", "p7"})
    assert card.labels.duel is True


def test_a_stack_card_is_not_a_duel():
    card = base_card(
        spectator({}), platform="euw1", riot_game_id="EUW1_1", tracked={"p1": 111, "p2": 222}
    )
    assert card.labels.duel is False


# -- rendu -----------------------------------------------------------------


def test_lock_embed_names_the_two_camps_in_a_duel():
    labels = side_labels_for([Tracked(100, "Gabite#EUW"), Tracked(200, "Mephisto#666")], 100)
    embed = build_lock_embed(
        riot_game_id="EUW1_1",
        tracked_names=["Gabite#EUW", "Mephisto#666"],
        pool=Pool(win_amount=300, loss_amount=100, win_count=2, loss_count=1),
        bets=[],
        tracked_team_name="Équipe Bleue",
        window_seconds=300,
        labels=labels,
    )
    names = " ".join(field.name for field in embed.fields)
    assert "Gabite" in names
    assert "Mephisto" in names
    assert "perd" not in names  # plus de formulation victoire/défaite


def duel_match() -> dict:
    parts = []
    for i in range(10):
        parts.append(
            {
                "puuid": f"p{i}",
                "riotIdGameName": f"Joueur{i}",
                "riotIdTagline": "EUW",
                "championId": 64,
                "championName": "LeeSin",
                "teamId": 100 if i < 5 else 200,
                "teamPosition": ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"][i % 5],
                "win": i < 5,
                "kills": 5,
                "deaths": 3,
                "assists": 5,
                "totalDamageDealtToChampions": 20000,
                "goldEarned": 12000,
                "totalMinionsKilled": 180,
                "neutralMinionsKilled": 0,
                "visionScore": 20,
                "totalDamageTaken": 20000,
                "damageSelfMitigated": 15000,
            }
        )
    return {
        "info": {
            "gameDuration": 1800,
            "gameEndTimestamp": 1,
            "participants": parts,
            "teams": [{"teamId": 100, "win": True}, {"teamId": 200, "win": False}],
        }
    }


def test_result_embed_titles_a_duel_by_the_winner():
    from lolbet.services.scoring import score_match

    scores = score_match(duel_match())
    embed = build_result_embed(
        riot_game_id="EUW1_1",
        queue_id=420,
        scores=scores,
        tracked_puuids={"p1", "p7"},
        tracked_team_id=100,
        settlement=None,
        ddragon=FakeDDragon(),
    )
    # p1 (bleu) gagne, p7 (rouge) perd : titrer « VICTOIRE » serait faux pour p7.
    assert "Joueur1" in embed.title
    assert "l'emporte" in embed.title
    assert len(embed) <= 6000


def test_result_embed_keeps_the_plain_title_without_a_duel():
    from lolbet.services.scoring import score_match

    scores = score_match(duel_match())
    embed = build_result_embed(
        riot_game_id="EUW1_1",
        queue_id=420,
        scores=scores,
        tracked_puuids={"p1"},
        tracked_team_id=100,
        settlement=None,
        ddragon=FakeDDragon(),
    )
    assert "VICTOIRE" in embed.title


def test_payouts_name_the_winning_camp_in_a_duel():
    from lolbet.services.scoring import score_match

    scores = score_match(duel_match())
    settlement = Settlement(
        winning_side=BetSide.WIN,
        pool=Pool(win_amount=300, loss_amount=100, win_count=1, loss_count=1),
        paid=[(111, 100, 400)],
        lost=[(222, 100)],
    )
    embed = build_result_embed(
        riot_game_id="EUW1_1",
        queue_id=420,
        scores=scores,
        tracked_puuids={"p1", "p7"},
        tracked_team_id=100,
        settlement=settlement,
        ddragon=FakeDDragon(),
    )
    payouts = next(f.value for f in embed.fields if "Gains" in f.name)
    assert "Joueur1" in payouts


# -- panneau de pari -------------------------------------------------------


def test_panel_shows_the_balance_and_the_commands():
    text = bet_panel_text(BetSide.WIN, 1000, Pool())
    assert "1 000" in text
    assert "/solde" in text
    assert "/quotidien" in text
    assert "/paris" in text
    assert "/annulerpari" in text


def test_panel_shows_the_current_odds_and_pool():
    pool = Pool(
        win_amount=300, loss_amount=100, win_count=2, loss_count=1,
        win_odds=1.33, loss_odds=4.0,
    )
    text = bet_panel_text(BetSide.WIN, 500, pool)
    assert "x1.33" in text
    assert "400" in text


def test_panel_says_when_no_one_backed_that_side_yet():
    pool = Pool(win_amount=0, loss_amount=100, win_count=0, loss_count=1)
    text = bet_panel_text(BetSide.WIN, 500, pool)
    assert "personne n'a encore parié" in text


def test_panel_uses_the_duel_labels():
    labels = side_labels_for([Tracked(100, "Gabite#EUW"), Tracked(200, "Mephisto#666")], 100)
    text = bet_panel_text(BetSide.WIN, 500, Pool(), labels)
    assert "Gabite" in text


def test_panel_points_a_broke_player_at_the_daily():
    text = bet_panel_text(BetSide.WIN, 0, Pool())
    assert "/quotidien" in text
    assert "plus rien à miser" in text
