"""/salon et /statut - réservés aux gestionnaires du serveur."""

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

# Les fils ne sont nécessaires que si LOLBET_USE_THREADS est activé.
BASE_PERMISSIONS = {"send_messages": "Envoyer des messages", "embed_links": "Intégrer des liens"}
THREAD_PERMISSIONS = {
    "create_public_threads": "Créer des fils publics",
    "send_messages_in_threads": "Envoyer des messages dans les fils",
}


class Admin(commands.Cog):
    def __init__(self, bot: LoLBet) -> None:
        self.bot = bot

    @app_commands.command(
        name="salon", description="Choisis où les parties en cours sont annoncées."
    )
    @app_commands.describe(channel="Salon textuel pour les annonces. Vide = le salon actuel.")
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
                "Choisis un salon textuel classique.", ephemeral=True
            )
            return

        needed = dict(BASE_PERMISSIONS)
        if self.bot.settings.use_threads:
            needed |= THREAD_PERMISSIONS

        me = target.guild.me
        permissions = target.permissions_for(me) if me else None
        missing = [
            label
            for name, label in needed.items()
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
                "\n\N{WARNING SIGN} Il me manque "
                + ", ".join(f"**{label}**" for label in missing)
                + " dans ce salon. Les annonces risquent d'échouer."
            )
        await interaction.response.send_message(
            f"Les parties seront annoncées dans {target.mention}.{note}", ephemeral=True
        )

    @app_commands.command(
        name="statut", description="Diagnostic du suivi, du cache et des limites Riot."
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
            else "non défini - lance `/salon`"
        )

        embed = discord.Embed(title="Statut de LoLBet", colour=discord.Colour(0x5865F2))
        embed.add_field(name="Salon d'annonce", value=channel, inline=False)
        embed.add_field(name="Joueurs inscrits", value=str(registered))
        embed.add_field(name="Parties en cours", value=str(live))
        embed.add_field(name="Résultats attendus", value=str(pending))
        embed.add_field(
            name="Limite de requêtes Riot",
            value="\n".join(f"{key} : {value}" for key, value in snapshot.items()),
            inline=False,
        )
        embed.add_field(name="Entrées en cache", value=str(self.bot.cache.size))
        embed.add_field(name="DDragon", value=self.bot.ddragon.version)
        embed.set_footer(
            text=(
                f"Sondage toutes les {self.bot.settings.poll_interval_seconds}s "
                "- SQLite sur disque local"
            )
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Cette commande est réservée aux gestionnaires du serveur.", ephemeral=True
            )
            return
        log.exception("admin.command_failed", error=str(error))
        if not interaction.response.is_done():
            await interaction.response.send_message("Ça n'a pas fonctionné.", ephemeral=True)


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Admin(bot))
