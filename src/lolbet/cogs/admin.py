"""/setchannel and /lolbet-status - guild administrator only."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from ..logging_conf import get_logger
from ..models import GameStatus, GuildConfig, Player, TrackedGame
from ..utils import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)

REQUIRED_PERMISSIONS = ("send_messages", "embed_links", "create_public_threads")


class Admin(commands.Cog):
    def __init__(self, bot: LoLBet) -> None:
        self.bot = bot

    @app_commands.command(description="Choose where live games get announced.")
    @app_commands.describe(channel="Text channel for announcements. Omit to use this one.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def setchannel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Pick a normal text channel.", ephemeral=True
            )
            return

        me = target.guild.me
        permissions = target.permissions_for(me) if me else None
        missing = [
            name
            for name in REQUIRED_PERMISSIONS
            if permissions is not None and not getattr(permissions, name, False)
        ]

        async with self.bot.session_factory() as session:
            config = await session.get(GuildConfig, interaction.guild_id or 0)
            if config is None:
                config = GuildConfig(guild_id=interaction.guild_id or 0)
            config.announce_channel_id = target.id
            config.updated_at = utcnow()
            session.add(config)
            await session.commit()

        note = ""
        if missing:
            note = (
                "\n\N{WARNING SIGN} I am missing "
                + ", ".join(f"`{name}`" for name in missing)
                + " there. Announcements or threads may fail."
            )
        await interaction.response.send_message(
            f"Live games will be announced in {target.mention}.{note}", ephemeral=True
        )

    @app_commands.command(
        name="lolbet-status", description="Tracker, cache and rate-limit diagnostics."
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        async with self.bot.session_factory() as session:
            registered = (
                await session.execute(
                    select(func.count(Player.id)).where(Player.guild_id == guild_id)
                )
            ).scalar_one()
            live = (
                await session.execute(
                    select(func.count(TrackedGame.id)).where(
                        TrackedGame.guild_id == guild_id,
                        TrackedGame.status.in_([GameStatus.LIVE, GameStatus.LOCKED]),
                    )
                )
            ).scalar_one()
            pending = (
                await session.execute(
                    select(func.count(TrackedGame.id)).where(
                        TrackedGame.guild_id == guild_id,
                        TrackedGame.status == GameStatus.PENDING_RESULT,
                    )
                )
            ).scalar_one()
            config = await session.get(GuildConfig, guild_id)

        snapshot = self.bot.limiter.snapshot()
        channel = (
            f"<#{config.announce_channel_id}>"
            if config and config.announce_channel_id
            else "not set - run `/setchannel`"
        )

        embed = discord.Embed(title="LoLBet status", colour=discord.Colour(0x5865F2))
        embed.add_field(name="Announce channel", value=channel, inline=False)
        embed.add_field(name="Registered players", value=str(registered))
        embed.add_field(name="Live games", value=str(live))
        embed.add_field(name="Awaiting results", value=str(pending))
        embed.add_field(
            name="Riot rate limit",
            value="\n".join(f"{key}: {value}" for key, value in snapshot.items()),
            inline=False,
        )
        embed.add_field(name="Cache entries", value=str(self.bot.cache.size))
        embed.add_field(name="DDragon", value=self.bot.ddragon.version)
        embed.set_footer(
            text=f"Poll every {self.bot.settings.poll_interval_seconds}s - SQLite on local disk"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "That one is for server managers only.", ephemeral=True
            )
            return
        log.exception("admin.command_failed", error=str(error))
        if not interaction.response.is_done():
            await interaction.response.send_message("That did not work.", ephemeral=True)


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Admin(bot))
