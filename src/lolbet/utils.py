"""Small helpers shared across the bot."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Timezone-aware "now". Every datetime we persist is UTC."""
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite hands datetimes back naive; re-attach UTC so comparisons work."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def from_epoch_ms(ms: int | float | None) -> datetime | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def format_duration(seconds: float | int) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}:{secs:02d}"


def format_points(value: int | float) -> str:
    """412345 becomes 412k, 1240000 becomes 1.2M."""
    value = int(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value // 1000}k"
    return str(value)


def format_coins(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_short_ago(moment: datetime | None, *, now: datetime | None = None) -> str:
    """Durée nue, pour les listes denses : ``4h``, ``2j``, ``1an``."""
    moment = as_utc(moment)
    if moment is None:
        return "?"
    now = as_utc(now) or utcnow()
    delta = (now - moment).total_seconds()
    if delta < 60:
        return "à l'instant"
    if delta < 3600:
        return f"{int(delta // 60)}min"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    days = int(delta // 86400)
    if days < 365:
        return f"{days}j"
    return f"{days // 365}an"


def format_ago(moment: datetime | None, *, now: datetime | None = None) -> str:
    """Durée en toutes lettres, pour les phrases : ``il y a 2j``."""
    if moment is None:
        return "jamais"
    short = format_short_ago(moment, now=now)
    return short if short == "à l'instant" else f"il y a {short}"


def discord_timestamp(moment: datetime, style: str = "R") -> str:
    """Discord renders these in each viewer own locale and timezone."""
    aware = as_utc(moment)
    assert aware is not None
    return f"<t:{int(aware.timestamp())}:{style}>"


def chunked(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]
