"""TTL cache: expiry, request coalescing and the SQLite mirror."""

from __future__ import annotations

import asyncio

from lolbet.riot.cache import TTL_MATCH, TTLCache
from tests.conftest import FakeClock


async def test_values_expire_after_their_ttl():
    clock = FakeClock()
    cache = TTLCache(persist=False, clock=clock)

    await cache.set("k", {"v": 1}, ttl=10)
    assert await cache.get("k") == {"v": 1}

    clock.now = 11
    assert await cache.get("k") is None


async def test_none_ttl_never_expires():
    """MATCH-V5 payloads are immutable, so they are kept forever."""
    clock = FakeClock()
    cache = TTLCache(persist=False, clock=clock)

    await cache.set("match:EUW1_1", {"info": {}}, ttl=TTL_MATCH)
    clock.now = 10**9
    assert await cache.get("match:EUW1_1") == {"info": {}}


async def test_get_or_set_calls_the_producer_once():
    cache = TTLCache(persist=False)
    calls = 0

    async def producer():
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_set("k", 60, producer) == 1
    assert await cache.get_or_set("k", 60, producer) == 1
    assert calls == 1


async def test_concurrent_misses_are_coalesced():
    """Five players in one game must not fire five identical lookups."""
    cache = TTLCache(persist=False)
    calls = 0

    async def slow_producer():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "value"

    results = await asyncio.gather(
        *(cache.get_or_set("shared", 60, slow_producer) for _ in range(5))
    )

    assert results == ["value"] * 5
    assert calls == 1


async def test_persistence_survives_a_restart(session_factory):
    cache = TTLCache(session_factory)
    await cache.set("account:puuid:abc", {"gameName": "Faker"}, ttl=3600)

    restarted = TTLCache(session_factory)
    assert await restarted.get("account:puuid:abc") is None  # not warmed yet

    loaded = await restarted.warm_from_disk()
    assert loaded == 1
    assert await restarted.get("account:puuid:abc") == {"gameName": "Faker"}


async def test_expired_rows_are_not_warmed_back(session_factory):
    clock = FakeClock()
    cache = TTLCache(session_factory, clock=clock)
    await cache.set("stale", 1, ttl=10)

    clock.now = 100
    restarted = TTLCache(session_factory, clock=clock)
    assert await restarted.warm_from_disk() == 0


async def test_purge_removes_expired_rows(session_factory):
    clock = FakeClock()
    cache = TTLCache(session_factory, clock=clock)
    await cache.set("a", 1, ttl=10)
    await cache.set("b", 2, ttl=None)

    clock.now = 50
    removed = await cache.purge_expired()

    assert removed == 1
    assert await cache.get("b") == 2


async def test_invalidate_drops_memory_and_disk(session_factory):
    cache = TTLCache(session_factory)
    await cache.set("k", 1, ttl=60)
    await cache.invalidate("k")

    assert await cache.get("k") is None
    restarted = TTLCache(session_factory)
    assert await restarted.warm_from_disk() == 0


async def test_unserialisable_values_do_not_raise(session_factory):
    cache = TTLCache(session_factory)
    await cache.set("weird", {1, 2, 3}, ttl=60)  # a set is not JSON
    assert await cache.get("weird") == {1, 2, 3}  # memory still works


async def test_locks_are_pruned():
    cache = TTLCache(persist=False)
    await cache.get_or_set("k", 60, lambda: _immediate(1))
    cache.prune_locks()
    assert cache.size == 1


async def _immediate(value):
    return value
