"""/salon et /statut - réservés aux gestionnaires du serveur."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from ..logging_conf import get_logger
from ..models import GameStatus, GuildConfig, Player, TrackedGame
from ..utils import discord_timestamp, utcnow

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)

# Les fils ne sont nécessaires que si LOLBET_USE_THREADS est activé.
BASE_PERMISSIONS = {"send_messages": "Envoyer des messages", "embed_links": "Intégrer des liens"}
THREAD_PERMISSIONS = {
    "create_public_threads": "Créer des fils publics",
    "send_messages_in_threads": "Envoyer des messages dans les fils",
}


def missing_permissions(
    channel: discord.TextChannel | None,
    me: discord.Member | None,
    *,
    with_threads: bool,
) -> list[str] | None:
    """Permissions manquantes pour annoncer. None = impossible a verifier."""
    if channel is None or me is None:
        return None
    needed = dict(BASE_PERMISSIONS)
    if with_threads:
        needed |= THREAD_PERMISSIONS
    permissions = channel.permissions_for(me)
    return [
        label for name, label in needed.items() if not getattr(permissions, name, False)
    ]


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

        missing = (
            missing_permissions(
                target, target.guild.me, with_threads=self.bot.settings.use_threads
            )
            or []
        )

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

        channel_id = config.announce_channel_id if config else None
        if not channel_id:
            channel = "non défini - lance `/salon`"
        else:
            target = self.bot.get_channel(channel_id)
            guild = interaction.guild
            missing = missing_permissions(
                target if isinstance(target, discord.TextChannel) else None,
                guild.me if guild else None,
                with_threads=self.bot.settings.use_threads,
            )
            if target is None:
                verdict = "\N{CROSS MARK} salon introuvable ou invisible pour moi"
            elif missing is None:
                verdict = "\N{WARNING SIGN} permissions non vérifiables"
            elif missing:
                # C'est la panne la plus silencieuse qui soit : le bot detecte
                # les parties, mais Discord refuse chaque annonce.
                verdict = "\N{CROSS MARK} il me manque " + ", ".join(
                    f"**{label}**" for label in missing
                )
            else:
                verdict = "\N{WHITE HEAVY CHECK MARK} je peux y poster"
            channel = f"<#{channel_id}>\n{verdict}"

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
        tracker = self.bot.tracker
        last_poll = (
            discord_timestamp(tracker.last_poll_at)
            if tracker.last_poll_at
            else "jamais"
        )
        embed.add_field(
            name="Sondage",
            value=(
                f"Dernier appel : {last_poll}\n"
                f"{tracker.last_pass_targets} joueur(s) surveillé(s) par passe\n"
                f"{tracker.polls_done} appels, {tracker.games_seen} parties vues"
            ),
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
