"""Comportement HTTP du client OverFast : cache, 404, 429, pannes.

OverFast est un service tiers gratuit qu'on ne paie pas et qu'on ne contrôle
pas. Le client doit donc être économe, et une panne de leur côté ne doit
jamais se traduire par un relevé faux — seulement par une absence de relevé.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from lolbet.overwatch.client import (
    OverFastClient,
    OverFastError,
    OwPlayerNotFound,
    OwUnavailable,
)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """Le repli est testé pour son enchaînement, pas pour sa durée."""

    async def instantly(_seconds: float) -> None:
        return None

    monkeypatch.setattr("lolbet.overwatch.client.asyncio.sleep", instantly)


BASE = "https://overfast-api.tekrop.fr"
TAG = "Joueur#1234"
SUMMARY_URL = f"{BASE}/players/Joueur-1234/summary"

PAYLOAD = {
    "username": "Joueur",
    "avatar": "https://example.invalid/a.png",
    "competitive": {
        "pc": {
            "season": 22,
            "tank": None,
            "damage": None,
            "support": {"division": "silver", "tier": 4},
            "open": None,
        },
        "console": None,
    },
}


@respx.mock
async def test_a_summary_is_cached(overfast: OverFastClient):
    route = respx.get(SUMMARY_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

    first = await overfast.get_summary(TAG)
    second = await overfast.get_summary(TAG)

    assert first == second
    assert route.call_count == 1  # le cache a absorbé la seconde lecture


@respx.mock
async def test_the_dash_form_hits_the_same_cache_entry(overfast: OverFastClient):
    route = respx.get(SUMMARY_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

    await overfast.get_summary("Joueur#1234")
    await overfast.get_summary("Joueur-1234")

    assert route.call_count == 1


@respx.mock
async def test_the_tracker_read_ignores_the_cache(overfast: OverFastClient):
    """Sinon un changement de rang serait vu avec dix minutes de retard."""
    route = respx.get(SUMMARY_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

    await overfast.get_summary(TAG)
    await overfast.refresh_summary(TAG)

    assert route.call_count == 2


@respx.mock
async def test_a_refresh_updates_the_cache(overfast: OverFastClient):
    route = respx.get(SUMMARY_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    await overfast.refresh_summary(TAG)
    after_refresh = route.call_count

    # Une lecture normale doit maintenant repartir du cache, sans requête.
    cached = await overfast.get_summary(TAG)

    assert cached["username"] == "Joueur"
    assert route.call_count == after_refresh


@respx.mock
async def test_an_unknown_player_raises_its_own_error(overfast: OverFastClient):
    respx.get(SUMMARY_URL).mock(
        return_value=httpx.Response(404, json={"error": "Player not found"})
    )
    with pytest.raises(OwPlayerNotFound):
        await overfast.get_summary(TAG)


@respx.mock
async def test_a_404_is_never_retried(overfast: OverFastClient):
    """Réessayer ne fera jamais apparaître un profil qui n'existe pas."""
    route = respx.get(SUMMARY_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(OwPlayerNotFound):
        await overfast.get_summary(TAG)
    assert route.call_count == 1


@respx.mock
async def test_a_server_error_is_retried_then_given_up(overfast: OverFastClient, settings):
    route = respx.get(SUMMARY_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(OwUnavailable):
        await overfast.get_summary(TAG)
    assert route.call_count == settings.max_retries + 1


@respx.mock
async def test_a_transient_error_recovers(overfast: OverFastClient):
    route = respx.get(SUMMARY_URL).mock(
        side_effect=[httpx.Response(502), httpx.Response(200, json=PAYLOAD)]
    )
    summary = await overfast.get_summary(TAG)
    assert summary["username"] == "Joueur"
    assert route.call_count == 2


@respx.mock
async def test_rate_limiting_backs_off_instead_of_hammering(overfast: OverFastClient):
    route = respx.get(SUMMARY_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json=PAYLOAD),
        ]
    )
    summary = await overfast.get_summary(TAG)
    assert summary["username"] == "Joueur"
    assert route.call_count == 2


@respx.mock
async def test_an_unexpected_status_is_surfaced(overfast: OverFastClient):
    respx.get(SUMMARY_URL).mock(return_value=httpx.Response(418, text="teapot"))
    with pytest.raises(OverFastError):
        await overfast.get_summary(TAG)


@respx.mock
async def test_a_failed_read_writes_nothing_to_the_cache(overfast: OverFastClient):
    """Une panne d'OverFast ne doit jamais devenir un relevé."""
    route = respx.get(SUMMARY_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(OwUnavailable):
        await overfast.get_summary(TAG)
    after_failure = route.call_count

    route.mock(return_value=httpx.Response(200, json=PAYLOAD))
    summary = await overfast.get_summary(TAG)
    assert summary["username"] == "Joueur"
    # Une vraie requête a bien été refaite : rien n'avait été mis en cache.
    assert route.call_count == after_failure + 1


@respx.mock
async def test_search_returns_the_results_list(overfast: OverFastClient):
    respx.get(f"{BASE}/players").mock(
        return_value=httpx.Response(
            200, json={"total": 1, "results": [{"name": "Joueur", "is_public": True}]}
        )
    )
    results = await overfast.search("Joueur")
    assert [row["name"] for row in results] == ["Joueur"]


@respx.mock
async def test_search_tolerates_an_empty_answer(overfast: OverFastClient):
    respx.get(f"{BASE}/players").mock(return_value=httpx.Response(200, json={"total": 0}))
    assert await overfast.search("personne") == []


@respx.mock
async def test_the_base_url_can_point_at_a_self_hosted_instance(settings, cache):
    """La contrainte du projet : pouvoir se passer de l'instance publique."""
    settings.overfast_base_url = "http://localhost:8000"
    client = OverFastClient(settings, cache)
    route = respx.get("http://localhost:8000/players/Joueur-1234/summary").mock(
        return_value=httpx.Response(200, json=PAYLOAD)
    )
    try:
        await client.get_summary(TAG)
    finally:
        await client.aclose()
    assert route.call_count == 1
