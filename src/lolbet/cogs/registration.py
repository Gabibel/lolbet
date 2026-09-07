"""/inscription, /profil, /classement, /inscrits, et les commandes d'admin.

Se désinscrire soi-même n'est volontairement pas possible : seul un
gestionnaire du serveur peut retirer un joueur, avec /desinscrire-joueur.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..config import VALID_PLATFORMS
from ..logging_conf import get_logger
from ..riot.client import RiotAPIError, RiotUnauthorized
from ..riot.rank import UNRANKED_LABEL, solo_queue_rank
from ..services.progression import lp_summary, summary_line
from ..services.registration import (
    LinkResult,
    RegistrationError,
    link_account,
    linked_players,
    unlink_account,
)
from ..utils import format_coins

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)

BAD_KEY_MESSAGE = (
    "La clé API Riot est expirée ou invalide, je ne peux chercher personne.\n"
    "Propriétaire du serveur : régénère-la sur <https://developer.riotgames.com/>, "
    "mets-la dans `.env` sous `LOLBET_RIOT_API_KEY`, puis redémarre le bot. "
    "Les clés de développement expirent toutes les 24 heures."
)
RIOT_DOWN_MESSAGE = "Riot n'a pas répondu. Réessaie dans un instant."


class Registration(commands.Cog):
    def __init__(self, bot: LoLBet) -> None:
        self.bot = bot

    async def platform_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        current = (current or "").lower()
        return [
            app_commands.Choice(name=platform, value=platform)
            for platform in sorted(VALID_PLATFORMS)
            if current in platform
        ][:25]

    async def _link(
        self,
        interaction: discord.Interaction,
        *,
        discord_id: int,
        riot_id: str,
        region: str | None,
    ) -> LinkResult | None:
        """Fait le lien et répond en cas d'échec. None = déjà répondu."""
        try:
            async with self.bot.session_factory() as session:
                result = await link_account(
                    session,
                    self.bot.riot,
                    self.bot.betting,
                    guild_id=interaction.guild_id or 0,
                    discord_id=discord_id,
                    riot_id=riot_id,
                    region=region,
                    default_platform=self.bot.settings.default_platform,
                )
                await session.commit()
        except RegistrationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return None
        except RiotUnauthorized as exc:
            # Réessayer ne servira à rien : la clé est expirée ou invalide.
            log.error("register.bad_api_key", error=str(exc))
            await interaction.followup.send(BAD_KEY_MESSAGE, ephemeral=True)
            return None
        except RiotAPIError as exc:
            log.warning("register.api_error", error=str(exc))
            await interaction.followup.send(RIOT_DOWN_MESSAGE, ephemeral=True)
            return None
        return result

    # -- inscription de soi-même ------------------------------------------

    @app_commands.command(
        name="inscription",
        description="Lie ton Riot ID pour que tes parties soient suivies ici.",
    )
    @app_commands.describe(
        riot_id="Ton Riot ID, par exemple Faker#KR1",
        region="Plateforme, par exemple euw1. Par défaut celle du serveur.",
    )
    @app_commands.autocomplete(region=platform_autocomplete)
    @app_commands.guild_only()
    async def register(
        self, interaction: discord.Interaction, riot_id: str, region: str | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self._link(
            interaction, discord_id=interaction.user.id, riot_id=riot_id, region=region
        )
        if result is None:
            return

        verb = "Inscrit" if result.created else "Mis à jour"
        await interaction.followup.send(
            f"{verb} : **{result.riot_id}** sur `{result.platform}`.\n"
            f"Tes parties seront annoncées ici. Solde : "
            f"**{format_coins(result.balance)}** pièces.",
            ephemeral=True,
        )

    # -- inscription de quelqu'un d'autre (admin) --------------------------

    @app_commands.command(
        name="inscrire-joueur",
        description="Inscris le compte LoL d'un autre membre du serveur.",
    )
    @app_commands.describe(
        membre="Le membre Discord à qui appartient le compte",
        riot_id="Son Riot ID, par exemple Faker#KR1",
        region="Plateforme, par exemple euw1. Par défaut celle du serveur.",
    )
    @app_commands.autocomplete(region=platform_autocomplete)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def register_player(
        self,
        interaction: discord.Interaction,
        membre: discord.User,
        riot_id: str,
        region: str | None = None,
    ) -> None:
        if membre.bot:
            await interaction.response.send_message(
                "Un bot ne joue pas à League of Legends.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self._link(
            interaction, discord_id=membre.id, riot_id=riot_id, region=region
        )
        if result is None:
            return

        verb = "Inscrit" if result.created else "Mis à jour"
        note = (
            ""
            if result.created
            else "\n\N{WARNING SIGN} Ce membre avait déjà un compte lié, il a été remplacé."
        )
        log.info(
            "register.by_admin",
            guild=interaction.guild_id,
            admin=interaction.user.id,
            target=membre.id,
        )
        await interaction.followup.send(
            f"{verb} : **{result.riot_id}** sur `{result.platform}` pour "
            f"{membre.mention}.\nSolde : **{format_coins(result.balance)}** pièces."
            f"{note}\nPense à le prévenir : ses parties seront annoncées publiquement.",
            ephemeral=True,
        )

    @app_commands.command(
        name="desinscrire-joueur",
        description="Retire le suivi du compte LoL d'un autre membre.",
    )
    @app_commands.describe(membre="Le membre à ne plus suivre")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def unregister_player(
        self, interaction: discord.Interaction, membre: discord.User
    ) -> None:
        async with self.bot.session_factory() as session:
            riot_id = await unlink_account(session, interaction.guild_id or 0, membre.id)
            await session.commit()

        if riot_id is None:
            await interaction.response.send_message(
                f"{membre.mention} n'a aucun compte lié ici.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"**{riot_id}** n'est plus suivi pour {membre.mention}. "
            "Ses pièces et son historique restent en place.",
            ephemeral=True,
        )

    @app_commands.command(
        name="inscrits", description="Liste les joueurs suivis sur ce serveur."
    )
    @app_commands.guild_only()
    async def registered(self, interaction: discord.Interaction) -> None:
        async with self.bot.session_factory() as session:
            players = await linked_players(session, interaction.guild_id or 0)

        if not players:
            await interaction.response.send_message(
                "Personne n'est inscrit. Utilise `/inscription`.", ephemeral=True
            )
            return

        lines = [
            f"<@{p.discord_id}> - **{discord.utils.escape_markdown(p.riot_id)}** "
            f"(`{p.platform}`)"
            for p in players
        ]
        embed = discord.Embed(
            title=f"Joueurs suivis ({len(players)})",
            description="\n".join(lines)[:4096],
            colour=discord.Colour(0x5865F2),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -- consultation ------------------------------------------------------

    @app_commands.command(
        name="profil", description="Affiche un joueur inscrit, son rang et ses pièces."
    )
    @app_commands.describe(user="De qui afficher le profil. Toi par défaut.")
    @app_commands.guild_only()
    async def profile(
        self, interaction: discord.Interaction, user: discord.User | None = None
    ) -> None:
        target = user or interaction.user
        guild_id = interaction.guild_id or 0

        async with self.bot.session_factory() as session:
            players = await linked_players(session, guild_id)
            player = next((p for p in players if p.discord_id == target.id), None)
            wallet = await self.bot.betting.get_wallet(
                session, guild_id, target.id, create=False
            )

        if player is None:
            await interaction.response.send_message(
                f"{target.mention} n'a pas encore lié de Riot ID ici. Essaie `/inscription`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        rank_line = UNRANKED_LABEL
        level_line = ""
        icon: int | None = None
        try:
            entries = await self.bot.riot.get_league_entries(player.puuid, player.platform)
            rank = solo_queue_rank(entries)
            if rank is not None:
                rank_line = rank.display
            summoner = await self.bot.riot.get_summoner(player.puuid, player.platform)
            if summoner:
                level_line = f"Niveau {summoner.get('summonerLevel', '?')}"
                icon = summoner.get("profileIconId")
        except RiotAPIError as exc:
            # Le rang est un bonus : on affiche le profil même si Riot est muet.
            log.warning("profile.api_error", error=str(exc))

        embed = discord.Embed(
            title=player.riot_id,
            colour=discord.Colour(0x5865F2),
            description=f"`{player.platform}` • {level_line}".strip(" •"),
        )
        if icon is not None:
            embed.set_thumbnail(url=self.bot.ddragon.profile_icon_url(int(icon)))
        embed.add_field(name="Solo/duo", value=rank_line, inline=False)

        async with self.bot.session_factory() as session:
            summary = await lp_summary(session, player.puuid)
        embed.add_field(
            name="LP suivis",
            value=(
                summary_line(summary)
                if summary.has_data
                else "Pas encore assez de relevés : il en faut deux, pris à la "
                "fin de deux parties suivies."
            ),
            inline=False,
        )
        embed.add_field(name="Solde", value=f"{format_coins(wallet.balance)} pièces")
        embed.add_field(
            name="Bilan des paris",
            value=(
                f"{wallet.bets_won}V / {wallet.bets_lost}D\n"
                f"Net {wallet.net_profit:+,} • misé {format_coins(wallet.total_wagered)}"
            ),
        )
        embed.set_footer(text=f"Suivi pour {target.display_name}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="classement", description="Les plus riches parieurs de ce serveur."
    )
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        async with self.bot.session_factory() as session:
            wallets = await self.bot.betting.leaderboard(session, guild_id, limit=10)
            registered = {
                player.discord_id: player.riot_id
                for player in await linked_players(session, guild_id)
            }

        if not wallets:
            await interaction.response.send_message(
                "Personne n'a encore parié.", ephemeral=True
            )
            return

        medals = ("\N{FIRST PLACE MEDAL}", "\N{SECOND PLACE MEDAL}", "\N{THIRD PLACE MEDAL}")
        lines = []
        for index, wallet in enumerate(wallets):
            prefix = medals[index] if index < len(medals) else f"`{index + 1:>2}.`"
            riot_id = registered.get(wallet.user_id)
            suffix = f" ({discord.utils.escape_markdown(riot_id)})" if riot_id else ""
            lines.append(
                f"{prefix} <@{wallet.user_id}>{suffix} - **{format_coins(wallet.balance)}** "
                f"({wallet.bets_won}V/{wallet.bets_lost}D, {wallet.net_profit:+,})"
            )

        embed = discord.Embed(
            title="Classement",
            description="\n".join(lines),
            colour=discord.Colour(0xF1C40F),
        )
        embed.set_footer(text="Pièces virtuelles uniquement.")
        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Cette commande est réservée aux gestionnaires du serveur.", ephemeral=True
            )
            return
        log.exception("registration.command_failed", error=str(error))
        if not interaction.response.is_done():
            await interaction.response.send_message("Ça n'a pas fonctionné.", ephemeral=True)


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Registration(bot))
