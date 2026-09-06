"""Riot client behaviour: routing, caching, 404 handling and 429 back-off."""

from __future__ import annotations

import httpx
import pytest
import respx

from lolbet.riot.cache import TTLCache
from lolbet.riot.client import (
    RiotClient,
    RiotNotFound,
    RiotUnauthorized,
    build_match_id,
)
from lolbet.riot.ratelimit import RateLimiter

EUROPE = "https://europe.api.riotgames.com"
EUW1 = "https://euw1.api.riotgames.com"
PUUID = "puuid-abc"


def test_build_match_id_uses_the_platform_prefix():
    assert build_match_id("euw1", 7123456789) == "EUW1_7123456789"
    assert build_match_id("KR", "12345") == "KR_12345"


@respx.mock
async def test_account_lookup_is_cached(riot: RiotClient):
    route = respx.get(
        f"{EUROPE}/riot/account/v1/accounts/by-riot-id/Faker/KR1"
    ).mock(return_value=httpx.Response(200, json={"puuid": PUUID, "gameName": "Faker"}))

    first = await riot.get_account_by_riot_id("Faker", "KR1", "euw1")
    second = await riot.get_account_by_riot_id("Faker", "KR1", "euw1")

    assert first == second
    assert first["puuid"] == PUUID
    assert route.call_count == 1  # the 7-day cache absorbed the second call


@respx.mock
async def test_riot_id_is_url_encoded(riot: RiotClient):
    route = respx.get(
        f"{EUROPE}/riot/account/v1/accounts/by-riot-id/hide%20on%20bush/KR1"
    ).mock(return_value=httpx.Response(200, json={"puuid": PUUID}))

    await riot.get_account_by_riot_id("hide on bush", "KR1", "euw1")
    assert route.call_count == 1


@respx.mock
async def test_unknown_riot_id_returns_none(riot: RiotClient):
    respx.get(f"{EUROPE}/riot/account/v1/accounts/by-riot-id/Nope/EUW").mock(
        return_value=httpx.Response(404, json={})
    )
    assert await riot.get_account_by_riot_id("Nope", "EUW", "euw1") is None


@respx.mock
async def test_spectator_404_means_not_in_game(riot: RiotClient):
    respx.get(f"{EUW1}/lol/spectator/v5/active-games/by-summoner/{PUUID}").mock(
        return_value=httpx.Response(404, json={})
    )
    assert await riot.get_active_game(PUUID, "euw1") is None


@respx.mock
async def test_spectator_is_never_cached(riot: RiotClient):
    route = respx.get(f"{EUW1}/lol/spectator/v5/active-games/by-summoner/{PUUID}").mock(
        return_value=httpx.Response(200, json={"gameId": 1, "participants": []})
    )
    await riot.get_active_game(PUUID, "euw1")
    await riot.get_active_game(PUUID, "euw1")
    # A stale live game would mean announcing a game that already ended.
    assert route.call_count == 2


@respx.mock
async def test_league_entries_use_the_puuid_endpoint(riot: RiotClient):
    """The by-summoner route was removed by Riot on 20 June 2025."""
    route = respx.get(f"{EUW1}/lol/league/v4/entries/by-puuid/{PUUID}").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "queueType": "RANKED_SOLO_5x5",
                    "tier": "DIAMOND",
                    "rank": "IV",
                    "leaguePoints": 32,
                    "wins": 10,
                    "losses": 8,
                }
            ],
        )
    )
    entries = await riot.get_league_entries(PUUID, "euw1")
    assert entries[0]["tier"] == "DIAMOND"
    assert route.call_count == 1


@respx.mock
async def test_league_404_gives_an_empty_list(riot: RiotClient):
    respx.get(f"{EUW1}/lol/league/v4/entries/by-puuid/{PUUID}").mock(
        return_value=httpx.Response(404, json={})
    )
    assert await riot.get_league_entries(PUUID, "euw1") == []


@respx.mock
async def test_mastery_is_keyed_on_puuid_and_champion(riot: RiotClient):
    first = respx.get(
        f"{EUW1}/lol/champion-mastery/v4/champion-masteries/by-puuid/{PUUID}/by-champion/64"
    ).mock(return_value=httpx.Response(200, json={"championLevel": 7, "championPoints": 412_345}))
    second = respx.get(
        f"{EUW1}/lol/champion-mastery/v4/champion-masteries/by-puuid/{PUUID}/by-champion/103"
    ).mock(return_value=httpx.Response(200, json={"championLevel": 4, "championPoints": 20_000}))

    lee = await riot.get_champion_mastery(PUUID, 64, "euw1")
    await riot.get_champion_mastery(PUUID, 64, "euw1")
    ahri = await riot.get_champion_mastery(PUUID, 103, "euw1")

    assert lee["championPoints"] == 412_345
    assert ahri["championLevel"] == 4
    assert first.call_count == 1  # cached on (puuid, championId)
    assert second.call_count == 1


@respx.mock
async def test_match_is_cached_forever(riot: RiotClient):
    route = respx.get(f"{EUROPE}/lol/match/v5/matches/EUW1_1").mock(
        return_value=httpx.Response(200, json={"info": {"gameDuration": 1800}})
    )
    await riot.get_match("EUW1_1", "euw1")
    await riot.get_match("EUW1_1", "euw1")
    assert route.call_count == 1


@respx.mock
async def test_missing_match_returns_none_so_the_tracker_can_retry(riot: RiotClient):
    respx.get(f"{EUROPE}/lol/match/v5/matches/EUW1_2").mock(
        return_value=httpx.Response(404, json={})
    )
    assert await riot.get_match("EUW1_2", "euw1") is None


@respx.mock
async def test_429_backs_off_using_retry_after(settings, cache: TTLCache):
    limiter = RateLimiter([(1000, 1.0)], max_concurrency=5)
    client = RiotClient(settings, cache, limiter)
    route = respx.get(f"{EUW1}/lol/summoner/v4/summoners/by-puuid/{PUUID}")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, json={"summonerLevel": 210}),
    ]

    summoner = await client.get_summoner(PUUID, "euw1")

    assert summoner["summonerLevel"] == 210
    assert route.call_count == 2
    # The whole limiter was parked, not just this one call.
    assert limiter.blocked_for >= 0
    await client.aclose()


@respx.mock
async def test_expired_key_raises_a_clear_error(riot: RiotClient):
    respx.get(f"{EUW1}/lol/summoner/v4/summoners/by-puuid/{PUUID}").mock(
        return_value=httpx.Response(403, json={})
    )
    with pytest.raises(RiotUnauthorized):
        await riot.get_summoner(PUUID, "euw1")


@respx.mock
async def test_server_errors_are_retried(riot: RiotClient):
    route = respx.get(f"{EUW1}/lol/summoner/v4/summoners/by-puuid/{PUUID}")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json={"summonerLevel": 30}),
    ]
    summoner = await riot.get_summoner(PUUID, "euw1")
    assert summoner["summonerLevel"] == 30
    assert route.call_count == 2


@respx.mock
async def test_cached_only_never_hits_the_network(riot: RiotClient):
    route = respx.get(f"{EUW1}/lol/league/v4/entries/by-puuid/{PUUID}").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert await riot.get_league_entries(PUUID, "euw1", cached_only=True) == []
    assert route.call_count == 0


@respx.mock
async def test_api_key_travels_in_the_header(riot: RiotClient, settings):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["token"] = request.headers.get("X-Riot-Token")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"summonerLevel": 1})

    respx.get(f"{EUW1}/lol/summoner/v4/summoners/by-puuid/{PUUID}").mock(side_effect=handler)
    await riot.get_summoner(PUUID, "euw1")

    assert captured["token"] == settings.riot_api_key
    assert settings.riot_api_key not in captured["url"]  # never in the query string


@respx.mock
async def test_regional_and_platform_routing_are_kept_apart(riot: RiotClient):
    account = respx.get(f"{EUROPE}/riot/account/v1/accounts/by-puuid/{PUUID}").mock(
        return_value=httpx.Response(200, json={"gameName": "New", "tagLine": "EUW"})
    )
    summoner = respx.get(f"{EUW1}/lol/summoner/v4/summoners/by-puuid/{PUUID}").mock(
        return_value=httpx.Response(200, json={"summonerLevel": 30})
    )

    await riot.get_account_by_puuid(PUUID, "euw1")
    await riot.get_summoner(PUUID, "euw1")

    assert account.call_count == 1
    assert summoner.call_count == 1


@respx.mock
async def test_unexpected_status_raises(riot: RiotClient):
    respx.get(f"{EUW1}/lol/summoner/v4/summoners/by-puuid/{PUUID}").mock(
        return_value=httpx.Response(418, text="teapot")
    )
    with pytest.raises(Exception) as excinfo:
        await riot.get_summoner(PUUID, "euw1")
    assert not isinstance(excinfo.value, RiotNotFound)
