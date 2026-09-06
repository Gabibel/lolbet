"""The rate limiter is the piece that keeps a dev key alive, so it gets the
most careful tests: both windows at once, 429 penalties, concurrency cap."""

from __future__ import annotations

import asyncio

import pytest

from lolbet.riot.ratelimit import RateLimiter, SlidingWindow, build_default_limiter
from tests.conftest import FakeClock


def test_sliding_window_allows_up_to_limit():
    window = SlidingWindow(3, 10.0)
    for _ in range(3):
        assert window.ready_at(0.0) == 0.0
        window.record(0.0)
    # Full: the next slot opens when the oldest hit ages out.
    assert window.ready_at(0.0) == 10.0


def test_sliding_window_prunes_old_hits():
    window = SlidingWindow(2, 10.0)
    window.record(0.0)
    window.record(1.0)

    # Full, so the next slot opens when the oldest hit ages out.
    assert window.ready_at(5.0) == 10.0

    # At t=10.5 only the t=0 hit has aged out.
    assert window.ready_at(10.5) == 10.5
    assert window.used == 1

    # At t=11 the t=1 hit is exactly one period old and goes too.
    assert window.ready_at(11.0) == 11.0
    assert window.used == 0


async def test_per_second_window_paces_requests():
    clock = FakeClock()
    limiter = RateLimiter([(2, 1.0), (100, 120.0)], clock=clock, sleep=clock.sleep)

    for _ in range(2):
        await limiter.acquire()
    assert clock.now == 0.0

    await limiter.acquire()
    assert clock.now == pytest.approx(1.0)


async def test_both_windows_are_honoured_together():
    """A burst allowed by the 1s window must still respect the 2min window."""
    clock = FakeClock()
    limiter = RateLimiter([(20, 1.0), (5, 120.0)], clock=clock, sleep=clock.sleep)

    for _ in range(5):
        await limiter.acquire()
    assert clock.now == 0.0  # the per-second window had room

    await limiter.acquire()
    assert clock.now == pytest.approx(120.0)  # blocked by the two-minute window


async def test_penalise_parks_every_caller():
    clock = FakeClock()
    limiter = RateLimiter([(100, 1.0)], clock=clock, sleep=clock.sleep)

    limiter.penalise(7.5)
    assert limiter.blocked_for == pytest.approx(7.5)

    await limiter.acquire()
    assert clock.now == pytest.approx(7.5)


async def test_penalise_keeps_the_longest_wait():
    clock = FakeClock()
    limiter = RateLimiter([(100, 1.0)], clock=clock, sleep=clock.sleep)
    limiter.penalise(10.0)
    limiter.penalise(2.0)
    assert limiter.blocked_for == pytest.approx(10.0)


async def test_zero_or_negative_retry_after_is_ignored():
    clock = FakeClock()
    limiter = RateLimiter([(100, 1.0)], clock=clock, sleep=clock.sleep)
    limiter.penalise(0)
    limiter.penalise(-5)
    assert limiter.blocked_for == 0.0


async def test_semaphore_caps_concurrency():
    limiter = RateLimiter([(1000, 1.0)], max_concurrency=3)
    inflight = 0
    peak = 0

    async def worker():
        nonlocal inflight, peak
        async with limiter.slot():
            inflight += 1
            peak = max(peak, inflight)
            await asyncio.sleep(0.01)
            inflight -= 1

    await asyncio.gather(*(worker() for _ in range(12)))
    assert peak <= 3


async def test_concurrent_acquires_never_exceed_the_window():
    """Ten coroutines racing must still only get `limit` slots per period."""
    clock = FakeClock()
    limiter = RateLimiter([(4, 1.0)], clock=clock, sleep=clock.sleep)
    starts: list[float] = []

    async def worker():
        await limiter.acquire()
        starts.append(clock.now)

    await asyncio.gather(*(worker() for _ in range(8)))
    assert sum(1 for start in starts if start < 1.0) == 4


def test_build_default_limiter_uses_both_riot_windows():
    limiter = build_default_limiter(20, 100, 5)
    snapshot = limiter.snapshot()
    assert "used_1s" in snapshot
    assert "used_120s" in snapshot


def test_invalid_windows_are_rejected():
    with pytest.raises(ValueError):
        SlidingWindow(0, 1.0)
    with pytest.raises(ValueError):
        SlidingWindow(1, 0)
    with pytest.raises(ValueError):
        RateLimiter([])
