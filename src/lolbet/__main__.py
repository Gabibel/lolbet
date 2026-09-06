"""Entry point: ``python -m lolbet`` or the ``lolbet`` console script."""

from __future__ import annotations

import asyncio
import sys

import discord

from .bot import LoLBet
from .config import get_settings
from .logging_conf import configure_logging, get_logger


async def run() -> int:
    try:
        settings = get_settings()
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        print("Copy .env.example to .env and fill in the two secrets.", file=sys.stderr)
        return 2

    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("lolbet")
    log.info(
        "bot.starting",
        platform=settings.default_platform,
        poll_interval=settings.poll_interval_seconds,
    )

    bot = LoLBet(settings)
    try:
        await bot.start(settings.discord_token)
    except discord.LoginFailure:
        log.error("bot.bad_token", hint="check LOLBET_DISCORD_TOKEN")
        return 2
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("bot.interrupted")
    finally:
        if not bot.is_closed():
            await bot.close()
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(run()))
    except KeyboardInterrupt:  # Ctrl-C during startup
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
