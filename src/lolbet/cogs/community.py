"""/recap, /trophees, /duel : ce qui fait vivre le serveur entre deux parties.

Trois commandes en lecture seule sur ``player_game_stat``, ``rank_snapshot``
et ``bet``. Aucune ne consomme de quota Riot : tout est déjà figé en base au
moment du règlement de chaque partie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..logging_conf import get_logger
from ..services.awards import missing_for, player_games, records_for, trophies_for
from ..services.digest import build_digest
from ..services.digest_embeds import (
    build_digest_embed,
    build_duel_embed,
    build_trophies_embed,
)
from ..services.headtohead import compare

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)


class Community(commands.Cog):
    def __init__(self, bot: LoLBet) -> None:
        self.bot = bot

    @app_commands.command(
        name="recap",
        description="Le bilan de la semaine : qui a joué, qui a monté, qui a nourri.",
    )
    @app_commands.describe(
        jours="Sur combien de jours regarder. Sept par défaut.",
    )
    @app_commands.guild_only()
    async def recap(
        self,
        interaction: discord.Interaction,
        jours: app_commands.Range[int, 1, 90] | None = None,
    ) -> None:
        days = jours or self.bot.settings.digest_days
        guild_id = interaction.guild_id or 0
        await interaction.response.defer()

        async with self.bot.session_factory() as session:
            digest = await build_digest(session, guild_id, days=days)

        await interaction.followup.send(embed=build_digest_embed(digest, days=days))

    @app_commands.command(
        name="trophees",
        description="Les trophées et les records d'un joueur.",
    )
    @app_commands.describe(membre="De qui. Toi par défaut.")
    @app_commands.guild_only()
    async def trophies(
        self, interaction: discord.Interaction, membre: discord.User | None = None
    ) -> None:
        target = membre or interaction.user
        guild_id = interaction.guild_id or 0
        await interaction.response.defer()

        async with self.bot.session_factory() as session:
            games = await player_games(session, guild_id, target.id)

        embed = build_trophies_embed(
            target,
            trophies_for(games),
            records_for(games),
            missing=missing_for(games),
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="duel",
        description="Compare deux joueurs, en général et sur leurs parties communes.",
    )
    @app_commands.describe(
        adversaire="Contre qui te comparer",
        membre="Qui comparer à l'adversaire. Toi par défaut.",
    )
    @app_commands.guild_only()
    async def duel(
        self,
        interaction: discord.Interaction,
        adversaire: discord.User,
        membre: discord.User | None = None,
    ) -> None:
        left = membre or interaction.user
        guild_id = interaction.guild_id or 0

        if left.id == adversaire.id:
            await interaction.response.send_message(
                "Se comparer à soi-même donne toujours une égalité.", ephemeral=True
            )
            return

        await interaction.response.defer()
        async with self.bot.session_factory() as session:
            duel = await compare(session, guild_id, left.id, adversaire.id)

        if not duel.left.games and not duel.right.games:
            await interaction.followup.send(
                "Aucun des deux n'a de partie suivie. Il faut jouer d'abord."
            )
            return

        await interaction.followup.send(embed=build_duel_embed(duel, left, adversaire))

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        log.exception("community.command_failed", error=str(error))
        if not interaction.response.is_done():
            await interaction.response.send_message("Ça n'a pas fonctionné.", ephemeral=True)


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Community(bot))
