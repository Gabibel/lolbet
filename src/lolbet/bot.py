"""The bot object: owns the engine, the Riot client and the background loops."""

from __future__ import annotations

import discord
from discord.ext import commands

from .config import Settings
from .db import create_engine, create_session_factory, init_db
from .logging_conf import get_logger
from .riot.cache import TTLCache
from .riot.client import RiotClient
from .riot.ddragon import DDragon
from .riot.ratelimit import build_default_limiter
from .services.betting import BettingService
from .services.messages import MessageUpdater
from .services.tracker import GameTracker
from .views import BetButton, CancelBetButton

log = get_logger(__name__)

COGS = (
    "lolbet.cogs.registration",
    "lolbet.cogs.betting",
    "lolbet.cogs.admin",
)


class LoLBet(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        # Only the default intents: no message content, no member list. The bot
        # works entirely through slash commands and its own messages.
        intents = discord.Intents.default()
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
        )
        self.settings = settings

        self.engine = create_engine(settings.database_url)
        self.session_factory = create_session_factory(self.engine)

        self.cache = TTLCache(self.session_factory)
        self.limiter = build_default_limiter(
            settings.rate_limit_per_second,
            settings.rate_limit_per_two_minutes,
            settings.max_concurrent_requests,
        )
        self.riot = RiotClient(settings, self.cache, self.limiter)
        self.ddragon = DDragon(self.cache)

        self.betting = BettingService(settings)
        self.updater = MessageUpdater(self)
        self.tracker = GameTracker(self)

    async def setup_hook(self) -> None:
        await init_db(self.engine)
        await self.cache.warm_from_disk()
        await self.ddragon.refresh()

        # Buttons carry their game id in the custom_id, so messages posted
        # before a restart keep working without re-registering per-game views.
        self.add_dynamic_items(BetButton, CancelBetButton)

        for cog in COGS:
            await self.load_extension(cog)

        await self._sync_commands()
        self.tracker.start()

    async def _sync_commands(self) -> None:
        try:
            if self.settings.dev_guild_id:
                guild = discord.Object(id=self.settings.dev_guild_id)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info("commands.synced", scope="guild", count=len(synced))

                # Commands previously synced globally survive until the global
                # set is rewritten. A command deleted from the code would keep
                # showing up, since a guild command only masks a global one of
                # the same name. Guild sync targets a single server anyway, so
                # emptying the global set is the honest end state.
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
                log.info("commands.global_cleared")
            else:
                synced = await self.tree.sync()
                log.info("commands.synced", scope="global", count=len(synced))
        except discord.Forbidden as exc:  # pragma: no cover - network
            log.error(
                "commands.sync_forbidden",
                error=str(exc),
                scope="guild" if self.settings.dev_guild_id else "global",
                hint=(
                    "check LOLBET_DEV_GUILD_ID, or invite the bot with the "
                    "applications.commands scope"
                ),
            )
        except discord.HTTPException as exc:  # pragma: no cover - network
            log.warning("commands.sync_failed", error=str(exc))

    async def on_ready(self) -> None:
        guild_ids = [guild.id for guild in self.guilds]
        log.info(
            "bot.ready",
            user=str(self.user),
            guilds=len(self.guilds),
            guild_ids=guild_ids[:10],
            ddragon=self.ddragon.version,
        )
        # A guild-scoped sync fails with 403 when the id does not match a guild
        # the bot is actually in - usually a channel id copied by mistake.
        dev_guild = self.settings.dev_guild_id
        if dev_guild and dev_guild not in guild_ids:
            log.error(
                "bot.dev_guild_mismatch",
                configured=dev_guild,
                actual=guild_ids[:10],
                hint="LOLBET_DEV_GUILD_ID is not a server this bot is in",
            )

    async def close(self) -> None:
        log.info("bot.closing")
        await self.tracker.stop()
        await self.updater.close()
        await self.riot.aclose()
        await self.ddragon.aclose()
        await super().close()
        await self.engine.dispose()
