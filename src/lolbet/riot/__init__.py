"""Riot API access: rate limiting, caching, HTTP client and static data."""

from .cache import TTLCache
from .client import (
    RiotAPIError,
    RiotClient,
    RiotNotFound,
    RiotUnauthorized,
    RiotUnavailable,
    build_match_id,
)
from .ddragon import DDragon
from .ratelimit import RateLimiter, build_default_limiter

__all__ = [
    "DDragon",
    "RateLimiter",
    "RiotAPIError",
    "RiotClient",
    "RiotNotFound",
    "RiotUnauthorized",
    "RiotUnavailable",
    "TTLCache",
    "build_default_limiter",
    "build_match_id",
]
