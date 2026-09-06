"""/inscription, /desinscription, /profil, /classement."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from ..config import VALID_PLATFORMS
from ..logging_conf import get_logger
from ..models import Player
from ..riot.client import RiotAPIError, RiotUnauthorized, normalise_platform
from ..riot.rank import UNRANKED_LABEL, solo_queue_rank
from ..utils import format_coins, utcnow

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)


def split_riot_id(raw: str) -> tuple[str, str] | None:
    """``Faker#KR1`` -> ``("Faker", "KR1")``. None si ce n'est pas un Riot ID."""
    text = (raw or "").strip()
    if "#" not in text:
        return None
    name, _, tag = text.rpartition("#")
    name, tag = name.strip(), tag.strip()
    if not name or not tag or len(name) > 16 or len(tag) > 5:
        return None
    return name, tag


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
        parts = split_riot_id(riot_id)
        if parts is None:
            await interaction.response.send_message(
                "Ça ne ressemble pas à un Riot ID. Utilise la forme `Pseudo#TAG`, "
                "par exemple `Faker#KR1`.",
                ephemeral=True,
            )
            return
        game_name, tag_line = parts
        platform = normalise_platform(region, self.bot.settings.default_platform)
        guild_id = interaction.guild_id or 0

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            account = await self.bot.riot.get_account_by_riot_id(game_name, tag_line, platform)
        except RiotUnauthorized as exc:
            # Réessayer ne servira à rien : la clé est expirée ou invalide.
            log.error("register.bad_api_key", error=str(exc))
            await interaction.followup.send(
                "La clé API Riot est expirée ou invalide, je ne peux chercher personne.\n"
                "Propriétaire du serveur : régénère-la sur "
                "<https://developer.riotgames.com/>, mets-la dans `.env` sous "
                "`LOLBET_RIOT_API_KEY`, puis redémarre le bot. "
                "Les clés de développement expirent toutes les 24 heures.",
                ephemeral=True,
            )
            return
        except RiotAPIError as exc:
            log.warning("register.api_error", error=str(exc))
            await interaction.followup.send(
                "Riot n'a pas répondu. Réessaie dans un instant.", ephemeral=True
            )
            return

        if not account or not account.get("puuid"):
            await interaction.followup.send(
                f"Aucun compte **{game_name}#{tag_line}** sur `{platform}`. "
                "Vérifie l'orthographe et la région.",
                ephemeral=True,
            )
            return

        puuid = str(account["puuid"])
        resolved_name = str(account.get("gameName") or game_name)
        resolved_tag = str(account.get("tagLine") or tag_line)

        async with self.bot.session_factory() as session:
            taken = (
                await session.execute(
                    select(Player).where(
                        Player.guild_id == guild_id,
                        Player.puuid == puuid,
                        Player.discord_id != interaction.user.id,
                    )
                )
            ).scalar_one_or_none()
            if taken is not None:
                await interaction.followup.send(
                    f"**{resolved_name}#{resolved_tag}** est déjà enregistré ici par "
                    f"<@{taken.discord_id}>.",
                    ephemeral=True,
                )
                return

            existing = (
                await session.execute(
                    select(Player).where(
                        Player.guild_id == guild_id, Player.discord_id == interaction.user.id
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    Player(
                        guild_id=guild_id,
                        discord_id=interaction.user.id,
                        puuid=puuid,
                        game_name=resolved_name,
                        tag_line=resolved_tag,
                        platform=platform,
                    )
                )
                verb = "Inscrit"
            else:
                existing.puuid = puuid
                existing.game_name = resolved_name
                existing.tag_line = resolved_tag
                existing.platform = platform
                existing.riot_id_refreshed_at = utcnow()
                session.add(existing)
                verb = "Mis à jour"

            wallet = await self.bot.betting.get_wallet(session, guild_id, interaction.user.id)
            await session.commit()

        await interaction.followup.send(
            f"{verb} : **{resolved_name}#{resolved_tag}** sur `{platform}`.\n"
            f"Tes parties seront annoncées ici. Solde : "
            f"**{format_coins(wallet.balance)}** pièces.",
            ephemeral=True,
        )

    @app_commands.command(
        name="desinscription", description="Arrête le suivi de ton compte sur ce serveur."
    )
    @app_commands.guild_only()
    async def unregister(self, interaction: discord.Interaction) -> None:
        async with self.bot.session_factory() as session:
            player = (
                await session.execute(
                    select(Player).where(
                        Player.guild_id == (interaction.guild_id or 0),
                        Player.discord_id == interaction.user.id,
                    )
                )
            ).scalar_one_or_none()
            if player is None:
                await interaction.response.send_message(
                    "Tu n'es pas inscrit ici.", ephemeral=True
                )
                return
            riot_id = player.riot_id
            await session.delete(player)
            await session.commit()

        await interaction.response.send_message(
            f"**{riot_id}** n'est plus suivi. Tes pièces et ton historique restent en place.",
            ephemeral=True,
        )

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
            player = (
                await session.execute(
                    select(Player).where(
                        Player.guild_id == guild_id, Player.discord_id == target.id
                    )
                )
            ).scalar_one_or_none()
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
                for player in (
                    await session.execute(select(Player).where(Player.guild_id == guild_id))
                )
                .scalars()
                .all()
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


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Registration(bot))
