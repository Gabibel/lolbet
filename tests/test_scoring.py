"""MVP / worst-player scoring."""

from __future__ import annotations

from lolbet.services.scoring import match_duration_seconds, score_match

POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def participant(
    *,
    puuid: str,
    team: int,
    position: str,
    win: bool,
    kills: int = 3,
    deaths: int = 3,
    assists: int = 5,
    damage: int = 15_000,
    gold: int = 10_000,
    cs: int = 150,
    vision: int = 20,
    taken: int = 20_000,
    mitigated: int = 15_000,
    dragons: int = 0,
    barons: int = 0,
    turrets: int = 0,
) -> dict:
    return {
        "puuid": puuid,
        "riotIdGameName": puuid,
        "riotIdTagline": "EUW",
        "championId": 64,
        "championName": "LeeSin",
        "teamId": team,
        "teamPosition": position,
        "win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "totalDamageDealtToChampions": damage,
        "goldEarned": gold,
        "totalMinionsKilled": cs,
        "neutralMinionsKilled": 0,
        "visionScore": vision,
        "totalDamageTaken": taken,
        "damageSelfMitigated": mitigated,
        "dragonKills": dragons,
        "baronKills": barons,
        "turretTakedowns": turrets,
        "inhibitorTakedowns": 0,
    }


def build_match(participants: list[dict], *, duration: int = 1800, winner: int = 100) -> dict:
    return {
        "info": {
            "gameDuration": duration,
            "gameEndTimestamp": 1_700_000_000_000,
            "queueId": 420,
            "participants": participants,
            "teams": [
                {"teamId": 100, "win": winner == 100},
                {"teamId": 200, "win": winner == 200},
            ],
        }
    }


def default_roster() -> list[dict]:
    people = []
    for team in (100, 200):
        for position in POSITIONS:
            people.append(
                participant(
                    puuid=f"{team}-{position}",
                    team=team,
                    position=position,
                    win=team == 100,
                )
            )
    return people


def test_duration_in_seconds_is_used_as_is():
    assert match_duration_seconds({"gameDuration": 1800, "gameEndTimestamp": 1}) == 1800


def test_legacy_millisecond_duration_is_converted():
    """Pre-11.20 matches report gameDuration in ms and have no end timestamp."""
    assert match_duration_seconds({"gameDuration": 1_800_000}) == 1800


def test_short_legacy_duration_is_not_mangled():
    assert match_duration_seconds({"gameDuration": 900}) == 900


def test_every_participant_is_scored():
    scores = score_match(build_match(default_roster()))
    assert len(scores.players) == 10
    assert scores.mvp is not None
    assert scores.worst is not None
    assert scores.mvp.puuid != scores.worst.puuid


def test_the_carry_is_mvp_and_the_feeder_is_worst():
    roster = default_roster()
    roster[2] = participant(  # blue mid
        puuid="carry",
        team=100,
        position="MIDDLE",
        win=True,
        kills=18,
        deaths=1,
        assists=9,
        damage=60_000,
        gold=20_000,
        cs=320,
    )
    roster[7] = participant(  # red mid
        puuid="feeder",
        team=200,
        position="MIDDLE",
        win=False,
        kills=0,
        deaths=14,
        assists=1,
        damage=3_000,
        gold=6_000,
        cs=40,
        vision=4,
        taken=5_000,
        mitigated=2_000,
    )
    scores = score_match(build_match(roster))

    assert scores.mvp.puuid == "carry"
    assert scores.worst.puuid == "feeder"


def test_a_support_is_not_punished_for_low_damage():
    """Role weights exist so vision-heavy supports stay competitive."""
    roster = default_roster()
    roster[4] = participant(
        puuid="support",
        team=100,
        position="UTILITY",
        win=True,
        kills=1,
        deaths=4,
        assists=24,
        damage=6_000,
        gold=8_000,
        cs=20,
        vision=90,
    )
    scores = score_match(build_match(roster))
    support = scores.by_puuid("support")
    same_team = [p for p in scores.team(100) if p.puuid != "support"]

    assert support is not None
    assert support.score > min(p.score for p in same_team)


def test_worst_player_can_come_from_the_winning_team():
    roster = default_roster()
    roster[0] = participant(
        puuid="afk-top",
        team=100,
        position="TOP",
        win=True,
        kills=0,
        deaths=12,
        assists=0,
        damage=1_000,
        gold=4_000,
        cs=10,
        vision=2,
        taken=3_000,
        mitigated=1_000,
    )
    scores = score_match(build_match(roster))
    assert scores.worst.puuid == "afk-top"
    assert scores.worst.win is True


def test_jungler_objectives_count():
    roster = default_roster()
    baseline = score_match(build_match(roster)).by_puuid("100-JUNGLE")

    roster[1] = participant(
        puuid="100-JUNGLE",
        team=100,
        position="JUNGLE",
        win=True,
        dragons=4,
        barons=1,
        turrets=3,
    )
    improved = score_match(build_match(roster)).by_puuid("100-JUNGLE")

    assert improved.score > baseline.score


def test_winning_team_and_kill_totals_are_reported():
    roster = default_roster()
    scores = score_match(build_match(roster, winner=200))
    assert scores.winning_team_id == 200
    assert scores.team_kills[100] == sum(p.kills for p in scores.team(100))


def test_empty_match_does_not_explode():
    scores = score_match({"info": {"participants": []}})
    assert scores.players == []
    assert scores.mvp is None
    assert scores.worst is None


def test_metrics_are_reported_for_the_recap():
    scores = score_match(build_match(default_roster()))
    reasons = scores.mvp.top_metrics()
    assert len(reasons) == 2
    assert all("%" in reason for reason in reasons)


def test_worst_player_reasons_are_their_weakest_areas():
    """The worst-player line must explain what sank them, not what went well."""
    roster = default_roster()
    roster[7] = participant(
        puuid="feeder",
        team=200,
        position="MIDDLE",
        win=False,
        kills=0,
        deaths=14,
        assists=1,
        damage=2_000,
        gold=6_000,
        cs=30,
        vision=3,
    )
    scores = score_match(build_match(roster))
    feeder = scores.by_puuid("feeder")

    assert feeder.bottom_metrics() != feeder.top_metrics()
    # Damage is the heaviest mid-lane weight and theirs is by far the worst.
    assert any("dégâts de l'équipe" in reason for reason in feeder.bottom_metrics(3))
    # Nobody in this match took an objective, so it is not a criticism.
    assert all("objectifs" not in reason for reason in feeder.bottom_metrics(3))


def test_a_support_is_never_criticised_for_farm():
    """Farm carries zero weight for UTILITY, so it is not a reason either way."""
    roster = default_roster()
    roster[4] = participant(
        puuid="support",
        team=100,
        position="UTILITY",
        win=True,
        cs=8,
        vision=70,
    )
    scores = score_match(build_match(roster))
    support = scores.by_puuid("support")

    assert support.weights["cs"] == 0
    assert all("farm" not in reason for reason in support.bottom_metrics())
    assert all("farm" not in reason for reason in support.top_metrics())


def test_missing_optional_fields_are_tolerated():
    """Old matches lack turretTakedowns, ARAM lacks teamPosition."""
    bare = [
        {"puuid": f"p{i}", "teamId": 100 if i < 5 else 200, "win": i < 5, "kills": i}
        for i in range(10)
    ]
    scores = score_match({"info": {"gameDuration": 1200, "participants": bare}})
    assert len(scores.players) == 10
    assert scores.mvp is not None
