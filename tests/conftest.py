from __future__ import annotations

import pytest

from lolbet.config import Settings
from lolbet.db import create_engine, create_session_factory, init_db
from lolbet.riot.cache import TTLCache
from lolbet.riot.client import RiotClient
from lolbet.riot.ratelimit import RateLimiter
from lolbet.services.betting import BettingService


class FakeClock:
    """Deterministic monotonic clock: sleeping just moves time forward."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        discord_token="test-token",
        riot_api_key="RGAPI-test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        default_platform="euw1",
        starting_balance=1000,
        daily_amount=100,
        min_bet=1,
        max_bet=100_000,
        max_retries=2,
        _env_file=None,
    )


@pytest.fixture
async def session_factory(settings):
    engine = create_engine(settings.database_url)
    await init_db(engine)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def cache() -> TTLCache:
    return TTLCache(session_factory=None, persist=False)


@pytest.fixture
def fast_limiter() -> RateLimiter:
    # Generous windows so client tests never actually wait.
    return RateLimiter([(1000, 1.0)], max_concurrency=5)


@pytest.fixture
def riot(settings, cache, fast_limiter) -> RiotClient:
    return RiotClient(settings, cache, fast_limiter)


@pytest.fixture
def betting(settings) -> BettingService:
    return BettingService(settings)
