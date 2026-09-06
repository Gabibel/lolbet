"""A single shared token bucket honouring every Riot rate-limit window at once.

A dev key allows 20 requests/second *and* 100 requests/2 minutes. Both windows
apply simultaneously, so one limiter tracks a list of windows and a request may
only start when every window has room. An additional semaphore caps in-flight
requests so a burst never spikes even when the windows would allow it.

On HTTP 429 the caller feeds Retry-After back in via :meth:`penalise`, which
parks the whole limiter until the penalty expires. Nothing ever busy-retries.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager

from ..logging_conf import get_logger

log = get_logger(__name__)


class SlidingWindow:
    """Counts request start times inside a rolling period."""

    __slots__ = ("limit", "period", "_hits")

    def __init__(self, limit: int, period: float) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if period <= 0:
            raise ValueError("period must be > 0")
        self.limit = limit
        self.period = float(period)
        self._hits: deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.period
        while self._hits and self._hits[0] <= cutoff:
            self._hits.popleft()

    def ready_at(self, now: float) -> float:
        """Earliest time a new request may start."""
        self._prune(now)
        if len(self._hits) < self.limit:
            return now
        # The oldest hit ages out of the window at hits[0] + period.
        return self._hits[0] + self.period

    def record(self, now: float) -> None:
        self._hits.append(now)

    @property
    def used(self) -> int:
        return len(self._hits)


class RateLimiter:
    """Fair-ish FIFO limiter across several windows plus a concurrency cap."""

    def __init__(
        self,
        windows: Iterable[tuple[int, float]],
        *,
        max_concurrency: int = 5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._windows = [SlidingWindow(limit, period) for limit, period in windows]
        if not self._windows:
            raise ValueError("at least one window is required")
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._lock = asyncio.Lock()
        self._blocked_until = 0.0
        self._clock = clock
        self._sleep = sleep

    async def acquire(self) -> None:
        """Block until a request may start, then charge it to every window."""
        while True:
            async with self._lock:
                now = self._clock()
                ready = max(
                    [self._blocked_until] + [w.ready_at(now) for w in self._windows]
                )
                if ready <= now:
                    for window in self._windows:
                        window.record(now)
                    return
                wait_for = ready - now
            # Sleep outside the lock so other coroutines can re-evaluate too.
            await self._sleep(wait_for)

    def penalise(self, retry_after: float) -> None:
        """Park every caller for ``retry_after`` seconds after a 429."""
        if retry_after <= 0:
            return
        until = self._clock() + retry_after
        if until > self._blocked_until:
            self._blocked_until = until
            log.warning("riot.rate_limited", retry_after=round(retry_after, 2))

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """Reserve a concurrency slot and a rate-limit token for one request."""
        await self._semaphore.acquire()
        try:
            await self.acquire()
            yield
        finally:
            self._semaphore.release()

    @property
    def blocked_for(self) -> float:
        return max(0.0, self._blocked_until - self._clock())

    def snapshot(self) -> dict[str, int | float]:
        now = self._clock()
        for window in self._windows:
            window.ready_at(now)  # prunes as a side effect
        return {
            f"used_{int(w.period)}s": w.used for w in self._windows
        } | {"blocked_for": round(self.blocked_for, 2)}


def build_default_limiter(
    per_second: int, per_two_minutes: int, max_concurrency: int
) -> RateLimiter:
    return RateLimiter(
        [(per_second, 1.0), (per_two_minutes, 120.0)],
        max_concurrency=max_concurrency,
    )
