"""Commandes Overwatch : /ow-inscription, /ow-profil, /ow-inscrits, admin.

Suivi de rang uniquement. Il n'y a pas de paris Overwatch, et ce n'est pas un
oubli : Blizzard ne publie ni les parties en cours ni les parties terminées,
donc il n'y a rien sur quoi ouvrir un marché ni rien pour le régler.

Comme du côté League, se désinscrire soi-même n'est pas possible : seul un
gestionnaire du serveur peut retirer un compte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..logging_conf import get_logger
from ..models import OverwatchPlayer
from ..overwatch.client import (
    InvalidBattleTag,
    OverFastError,
    OwPlayerNotFound,
    normalise_battletag,
)
from ..overwatch.rank import PLATFORMS, ROLES, busiest_platform, parse_summary, season_of
from ..services.ow_embeds import (
    build_ow_profile_embed,
    build_ow_roster_embed,
)
from ..services.overwatch import (
    apply_ranks,
    latest_ow_ranks,
    latest_ow_snapshot,
    linked_ow_players,
    ow_player_for,
    peak_rank,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)

OVERFAST_DOWN = (
    "Le service qui lit les profils Overwatch n'a pas répondu. "
    "Réessaie dans un moment."
)
NOT_FOUND = (
    "Aucun profil trouvé pour ce BattleTag. Vérifie l'orthographe "
    "(`Pseudo#1234`), et que le profil de carrière est bien en public dans "
    "les options du jeu : Options → Social → Profil de carrière."
)
DISABLED = "Le suivi Overwatch est désactivé sur ce bot."


class Overwatch(commands.Cog):
    def __init__(self, bot: LoLBet) -> None:
        self.bot = bot

    async def platform_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        current = (current or "").lower()
        return [
            app_commands.Choice(name="PC" if p == "pc" else "Console", value=p)
            for p in PLATFORMS
            if current in p
        ]

    # -- inscription -------------------------------------------------------

    async def _link(
        self,
        interaction: discord.Interaction,
        *,
        member: discord.User | discord.Member,
        battletag: str,
        platform: str | None,
    ) -> None:
        if not self.bot.settings.overwatch_enabled:
            await interaction.response.send_message(DISABLED, ephemeral=True)
            return

        try:
            tag = normalise_battletag(battletag)
        except InvalidBattleTag as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            summary = await self.bot.overfast.get_summary(tag)
        except OwPlayerNotFound:
            await interaction.followup.send(NOT_FOUND, ephemeral=True)
            return
        except OverFastError as exc:
            log.warning("ow.link_failed", battletag=tag, error=str(exc))
            await interaction.followup.send(OVERFAST_DOWN, ephemeral=True)
            return

        # Plateforme choisie explicitement, sinon celle où il a un rang.
        chosen = platform or busiest_platform(summary)
        ranks = parse_summary(summary, chosen)
        guild_id = interaction.guild_id or 0

        async with self.bot.session_factory() as session:
            existing = await ow_player_for(session, guild_id, member.id)
            player = existing or OverwatchPlayer(
                guild_id=guild_id, discord_id=member.id, battletag=tag
            )
            player.battletag = tag
            player.platform = chosen
            player.username = summary.get("username") or tag.split("#")[0]
            player.avatar_url = summary.get("avatar") or ""
            player.last_error = "" if ranks else "aucun rang compétitif visible"
            session.add(player)
            await session.flush()

            # Premier relevé : il sert de référence, il n'est pas annoncé.
            await apply_ranks(
                session,
                battletag=tag,
                platform=chosen,
                ranks=ranks,
                season=season_of(summary, chosen),
            )
            await session.commit()

        verb = "mis à jour" if existing else "inscrit"
        summary_line = (
            " \N{BULLET} ".join(ranks[role].display for role in ROLES if role in ranks)
            or "aucun rang compétitif visible pour l'instant"
        )
        await interaction.followup.send(
            f"{member.mention} {verb} sur `{tag}` ({_platform_label(chosen)}).\n"
            f"{summary_line}\n"
            "Je relis le profil régulièrement et j'annonce les changements de rang. "
            "Le jeu ne réévalue que toutes les 5 victoires ou 15 défaites, donc "
            "c'est normal que ça ne bouge pas à chaque partie.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ow-inscription",
        description="Lie ton compte Overwatch pour suivre ton rang.",
    )
    @app_commands.describe(
        battletag="Ton BattleTag, par exemple Pseudo#1234",
        plateforme="PC ou console. Deviné automatiquement si tu ne mets rien.",
    )
    @app_commands.autocomplete(plateforme=platform_autocomplete)
    @app_commands.guild_only()
    async def register(
        self,
        interaction: discord.Interaction,
        battletag: str,
        plateforme: str | None = None,
    ) -> None:
        await self._link(
            interaction,
            member=interaction.user,
            battletag=battletag,
            platform=plateforme,
        )

    @app_commands.command(
        name="ow-inscrire-joueur",
        description="Inscris le compte Overwatch d'un autre membre.",
    )
    @app_commands.describe(
        membre="Le membre Discord à qui appartient le compte",
        battletag="Son BattleTag, par exemple Pseudo#1234",
        plateforme="PC ou console. Deviné automatiquement si tu ne mets rien.",
    )
    @app_commands.autocomplete(plateforme=platform_autocomplete)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def register_player(
        self,
        interaction: discord.Interaction,
        membre: discord.User,
        battletag: str,
        plateforme: str | None = None,
    ) -> None:
        await self._link(
            interaction, member=membre, battletag=battletag, platform=plateforme
        )

    @app_commands.command(
        name="ow-desinscrire-joueur",
        description="Retire le compte Overwatch d'un membre.",
    )
    @app_commands.describe(membre="Le membre à retirer du suivi")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def unregister_player(
        self, interaction: discord.Interaction, membre: discord.User
    ) -> None:
        guild_id = interaction.guild_id or 0
        async with self.bot.session_factory() as session:
            player = await ow_player_for(session, guild_id, membre.id)
            if player is None:
                await interaction.response.send_message(
                    f"{membre.mention} n'a pas de compte Overwatch suivi ici.",
                    ephemeral=True,
                )
                return
            tag = player.battletag
            await session.delete(player)
            await session.commit()

        # Les relevés sont gardés : ils valent plus que l'inscription, et une
        # réinscription retrouve l'historique.
        await interaction.response.send_message(
            f"`{tag}` n'est plus suivi. Les relevés de rang sont conservés.",
            ephemeral=True,
        )

    # -- consultation ------------------------------------------------------

    @app_commands.command(
        name="ow-profil",
        description="Affiche le rang Overwatch d'un membre inscrit.",
    )
    @app_commands.describe(membre="De qui afficher le profil. Toi par défaut.")
    @app_commands.guild_only()
    async def profile(
        self, interaction: discord.Interaction, membre: discord.User | None = None
    ) -> None:
        target = membre or interaction.user
        guild_id = interaction.guild_id or 0

        async with self.bot.session_factory() as session:
            player = await ow_player_for(session, guild_id, target.id)
            if player is None:
                await interaction.response.send_message(
                    f"{target.mention} n'a pas encore lié de BattleTag ici. "
                    "Essaie `/ow-inscription`.",
                    ephemeral=True,
                )
                return

            ranks = await latest_ow_ranks(session, player.battletag, player.platform)
            peaks = {
                role: snapshot
                for role in ROLES
                if (
                    snapshot := await peak_rank(
                        session, player.battletag, role, player.platform
                    )
                )
                is not None
            }
            last_move = await _last_move(session, player)

        embed = build_ow_profile_embed(
            player,
            ranks,
            peaks=peaks,
            last_move=last_move,
            checked_at=player.last_checked_at,
        )
        if player.last_error:
            embed.add_field(
                name="Dernière lecture", value=player.last_error, inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="ow-inscrits",
        description="Liste les comptes Overwatch suivis sur ce serveur.",
    )
    @app_commands.guild_only()
    async def roster(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        await interaction.response.defer()
        async with self.bot.session_factory() as session:
            players = await linked_ow_players(session, guild_id)
            entries = [
                (
                    player,
                    await latest_ow_ranks(session, player.battletag, player.platform),
                )
                for player in players
            ]
        await interaction.followup.send(embed=build_ow_roster_embed(entries))


async def _last_move(session, player: OverwatchPlayer):  # noqa: ANN001
    """Le relevé le plus récent, tous rôles confondus."""
    newest = None
    for role in ROLES:
        snapshot = await latest_ow_snapshot(
            session, player.battletag, role, player.platform
        )
        if snapshot is None:
            continue
        if newest is None or snapshot.captured_at > newest.captured_at:
            newest = snapshot
    return newest


def _platform_label(platform: str) -> str:
    return "PC" if platform == "pc" else "Console"


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Overwatch(bot))
