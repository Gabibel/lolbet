"""Editing the announcement message, with debounced edits.

Every bet would otherwise trigger an embed edit, and Discord rate-limits edits
per channel. Instead, a bet schedules a refresh: the first one starts a timer,
any further bets inside the window ride along with it, and one edit at the end
shows the final pool.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import discord
from sqlalchemy import select

from ..logging_conf import get_logger
from ..models import TrackedGame, TrackedParticipant
from ..utils import as_utc
from .embeds import build_game_embed
from .enrichment import build_card

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)


class MessageUpdater:
    def __init__(self, bot: LoLBet) -> None:
        self._bot = bot
        self._tasks: dict[int, asyncio.Task[None]] = {}

    # -- scheduling -------------------------------------------------------

    def schedule(self, game_id: int) -> None:
        """Ask for a refresh soon. Repeated calls collapse into one edit."""
        task = self._tasks.get(game_id)
        if task is not None and not task.done():
            return
        self._tasks[game_id] = asyncio.create_task(self._debounced(game_id))

    async def _debounced(self, game_id: int) -> None:
        try:
            await asyncio.sleep(self._bot.settings.embed_edit_debounce_seconds)
            await self.refresh(game_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a failed redraw must not kill the bot
            log.warning("updater.refresh_failed", game_id=game_id, error=str(exc))
        finally:
            self._tasks.pop(game_id, None)

    async def close(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    # -- rendering --------------------------------------------------------

    async def refresh(self, game_id: int, *, allow_fetch: bool = False) -> None:
        """Redraw the announcement embed for one game.

        ``allow_fetch`` is only true for the phase-2 enrichment pass; ordinary
        odds refreshes read the warm cache and never spend Riot quota.
        """
        bot = self._bot
        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            if game is None or not game.message_id or not game.channel_id:
                return
            participants = (
                (
                    await session.execute(
                        select(TrackedParticipant).where(TrackedParticipant.game_id == game_id)
                    )
                )
                .scalars()
                .all()
            )
            pool = await bot.betting.pool(session, game_id)

        try:
            spectator = json.loads(game.spectator_json or "{}")
        except ValueError:
            spectator = {}
        if not spectator:
            return

        tracked = {p.puuid: p.discord_id for p in participants}
        card = await build_card(
            spectator,
            bot.riot,
            bot.ddragon,
            platform=game.platform,
            riot_game_id=game.riot_game_id,
            tracked=tracked,
            lock_at=as_utc(game.lock_at),
            enrich=True,
            cached_only=not allow_fetch,
        )
        card.tracked_team_id = game.tracked_team_id
        card.enriched = card.enriched or game.enriched

        embed = build_game_embed(card, pool, bot.ddragon, status=game.status)

        from ..views import view_for  # local import avoids a circular import

        await self.edit(game, embed=embed, view=view_for(game))

        if allow_fetch and card.enriched and not game.enriched:
            async with bot.session_factory() as session:
                stored = await session.get(TrackedGame, game_id)
                if stored is not None:
                    stored.enriched = True
                    session.add(stored)
                    await session.commit()

    async def edit(
        self,
        game: TrackedGame,
        *,
        embed: discord.Embed,
        view: discord.ui.View | None,
    ) -> None:
        message = self.partial_message(game)
        if message is None:
            return
        try:
            await message.edit(embed=embed, view=view)
        except discord.NotFound:
            log.warning("updater.message_gone", game_id=game.id)
        except discord.Forbidden:
            log.warning("updater.forbidden", channel_id=game.channel_id)
        except discord.HTTPException as exc:
            log.warning("updater.http_error", game_id=game.id, error=str(exc))

    def partial_message(self, game: TrackedGame) -> discord.PartialMessage | None:
        if not game.channel_id or not game.message_id:
            return None
        channel = self._bot.get_channel(game.channel_id)
        if not isinstance(channel, discord.abc.Messageable) or not hasattr(
            channel, "get_partial_message"
        ):
            return None
        return channel.get_partial_message(game.message_id)  # type: ignore[union-attr]

    async def destination(self, game: TrackedGame) -> discord.abc.Messageable | None:
        """Where the recap goes: the game thread, else the announce channel."""
        if game.thread_id:
            thread = self._bot.get_channel(game.thread_id)
            if isinstance(thread, discord.abc.Messageable):
                return thread
            try:
                fetched = await self._bot.fetch_channel(game.thread_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                fetched = None
            if isinstance(fetched, discord.abc.Messageable):
                return fetched
        if game.channel_id:
            channel = self._bot.get_channel(game.channel_id)
            if isinstance(channel, discord.abc.Messageable):
                return channel
        return None
