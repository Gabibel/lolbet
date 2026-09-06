"""Rank ladder maths, spectator parsing and bet-amount parsing."""

from __future__ import annotations

import pytest

from lolbet.riot.rank import (
    RankInfo,
    average_score,
    score_to_label,
    solo_queue_rank,
)
from lolbet.services.enrichment import base_card, find_team_id, parse_riot_id
from lolbet.utils import format_ago, format_duration, format_points, from_epoch_ms
from lolbet.views import AmountError, parse_amount

# -- ranks -----------------------------------------------------------------


def test_ladder_score_increases_with_tier_division_and_lp():
    iron4 = RankInfo("RANKED_SOLO_5x5", "IRON", "IV", 0)
    iron1 = RankInfo("RANKED_SOLO_5x5", "IRON", "I", 0)
    bronze4 = RankInfo("RANKED_SOLO_5x5", "BRONZE", "IV", 0)
    diamond1 = RankInfo("RANKED_SOLO_5x5", "DIAMOND", "I", 75)

    assert iron4.score < iron1.score < bronze4.score < diamond1.score


def test_master_and_above_share_one_lp_pool():
    master = RankInfo("RANKED_SOLO_5x5", "MASTER", "I", 120)
    challenger = RankInfo("RANKED_SOLO_5x5", "CHALLENGER", "I", 1200)
    diamond1 = RankInfo("RANKED_SOLO_5x5", "DIAMOND", "I", 100)

    assert master.score > diamond1.score
    assert challenger.score > master.score


def test_short_and_display_forms():
    diamond = RankInfo("RANKED_SOLO_5x5", "DIAMOND", "IV", 32, wins=10, losses=10)
    assert diamond.short == "D4 32LP"
    assert "Diamant IV" in diamond.display
    assert "50%" in diamond.display

    master = RankInfo("RANKED_SOLO_5x5", "MASTER", "I", 300)
    assert master.short == "M 300LP"
    assert "Maître" in master.display


def test_score_to_label_round_trips():
    """Les paliers viennent de l'API en anglais, l'affichage est en français."""
    expected = {"GOLD": "Or", "EMERALD": "Émeraude", "IRON": "Fer"}
    for tier, division in (("GOLD", "II"), ("EMERALD", "IV"), ("IRON", "I")):
        rank = RankInfo("RANKED_SOLO_5x5", tier, division, 50)
        assert score_to_label(rank.score) == f"{expected[tier]} {division}"


def test_solo_queue_is_preferred_over_flex():
    entries = [
        {"queueType": "RANKED_FLEX_SR", "tier": "PLATINUM", "rank": "I", "leaguePoints": 10},
        {"queueType": "RANKED_SOLO_5x5", "tier": "GOLD", "rank": "IV", "leaguePoints": 0},
    ]
    rank = solo_queue_rank(entries)
    assert rank.tier == "GOLD"


def test_flex_is_used_when_there_is_no_solo_rank():
    entries = [
        {"queueType": "RANKED_FLEX_SR", "tier": "PLATINUM", "rank": "I", "leaguePoints": 10}
    ]
    assert solo_queue_rank(entries).tier == "PLATINUM"


def test_unranked_players_have_no_rank():
    assert solo_queue_rank([]) is None
    assert solo_queue_rank(None) is None


def test_average_score_ignores_unranked_players():
    gold = RankInfo("RANKED_SOLO_5x5", "GOLD", "IV", 0)
    plat = RankInfo("RANKED_SOLO_5x5", "PLATINUM", "IV", 0)
    assert average_score([gold, plat, None]) == pytest.approx((gold.score + plat.score) / 2)
    assert average_score([None, None]) is None


# -- spectator parsing -----------------------------------------------------


def spectator_payload() -> dict:
    return {
        "gameId": 7123456789,
        "gameQueueConfigId": 420,
        "gameStartTime": 1_700_000_000_000,
        "participants": [
            {
                "puuid": f"p{i}",
                "teamId": 100 if i < 5 else 200,
                "championId": 100 + i,
                "spell1Id": 4,
                "spell2Id": 14,
                "riotId": f"Player{i}#EUW",
            }
            for i in range(10)
        ],
    }


def test_parse_riot_id_handles_missing_tags():
    assert parse_riot_id("Faker#KR1") == ("Faker", "KR1")
    assert parse_riot_id(None) == ("Unknown", "")
    assert parse_riot_id("NoTag") == ("NoTag", "")


def test_find_team_id_uses_the_tracked_player():
    payload = spectator_payload()
    assert find_team_id(payload, {"p2"}) == 100
    assert find_team_id(payload, {"p7"}) == 200
    assert find_team_id(payload, {"unknown"}) == 100  # sane default


def test_base_card_needs_no_extra_api_calls():
    card = base_card(
        spectator_payload(),
        platform="euw1",
        riot_game_id="EUW1_7123456789",
        tracked={"p3": 999},
    )

    assert len(card.players) == 10
    assert len(card.team(100)) == 5
    assert card.queue_id == 420
    assert card.tracked_team_id == 100
    assert card.enriched is False

    tracked = card.tracked
    assert len(tracked) == 1
    assert tracked[0].discord_id == 999
    assert tracked[0].riot_id == "Player3#EUW"
    # Phase 1 has no rank or mastery yet - that is the whole point.
    assert tracked[0].rank is None
    assert tracked[0].mastery_points is None


def test_base_card_reads_the_start_time():
    card = base_card(
        spectator_payload(), platform="euw1", riot_game_id="EUW1_1", tracked={}
    )
    assert card.started_at == from_epoch_ms(1_700_000_000_000)


# -- bet amounts -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("250", 250),
        (" 1 000 ", 1000),
        ("1,500", 1500),
        ("2k", 2000),
        ("1.5k", 1500),
        ("1m", 1_000_000),
        ("all", 800),
        ("max", 800),
        ("half", 400),
        ("50%", 400),
        ("25%", 200),
    ],
)
def test_parse_amount_accepts_shorthand(raw, expected):
    assert parse_amount(raw, balance=800) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abc", "-", "1e999k", "0%", "150%", "%"])
def test_parse_amount_rejects_nonsense(raw):
    with pytest.raises(AmountError):
        parse_amount(raw, balance=800)


def test_parse_amount_of_a_negative_number_is_left_to_the_service():
    # Parsing succeeds; the minimum-bet rule in BettingService rejects it.
    assert parse_amount("-50", balance=800) == -50


# -- formatting ------------------------------------------------------------


def test_format_points_is_compact():
    assert format_points(412_345) == "412k"
    assert format_points(1_240_000) == "1.2M"
    assert format_points(900) == "900"


def test_format_duration_reads_like_a_game_clock():
    assert format_duration(1830) == "30:30"
    assert format_duration(-5) == "0:00"
    assert format_duration(3661) == "1h 01m 01s"


def test_format_ago_is_human():
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert format_ago(now - timedelta(minutes=30), now=now) == "30m ago"
    assert format_ago(now - timedelta(days=2), now=now) == "2d ago"
    assert format_ago(None) == "never"


# -- lock notice -----------------------------------------------------------


class _FakeBet:
    def __init__(self, user_id: int, side: str, amount: int) -> None:
        self.user_id, self.side, self.amount = user_id, side, amount


def test_lock_embed_lists_both_sides_and_their_bettors():
    from lolbet.models import BetSide
    from lolbet.services.betting import Pool
    from lolbet.services.embeds import build_lock_embed

    pool = Pool(win_amount=300, loss_amount=100, win_count=2, loss_count=1)
    bets = [
        _FakeBet(11, BetSide.WIN, 200),
        _FakeBet(22, BetSide.WIN, 100),
        _FakeBet(33, BetSide.LOSS, 100),
    ]
    embed = build_lock_embed(
        riot_game_id="EUW1_1",
        tracked_names=["Gabite#EUW"],
        pool=pool,
        bets=bets,
        tracked_team_name="Blue Team",
        window_seconds=300,
    )

    assert "Paris fermés" in embed.title
    assert "5 minutes" in embed.description
    win_field, loss_field = embed.fields
    assert "300" in win_field.name and "x1.33" in win_field.name
    assert "<@11>" in win_field.value and "<@22>" in win_field.value
    assert "<@33>" in loss_field.value
    assert len(embed) <= 6000


def test_lock_embed_says_nobody_when_there_were_no_bets():
    from lolbet.services.betting import Pool
    from lolbet.services.embeds import build_lock_embed

    embed = build_lock_embed(
        riot_game_id="EUW1_1",
        tracked_names=["Gabite#EUW"],
        pool=Pool(),
        bets=[],
        tracked_team_name="Blue Team",
        window_seconds=300,
    )
    assert "Personne n'a parié" in embed.description
    assert all(field.value == "Personne" for field in embed.fields)
