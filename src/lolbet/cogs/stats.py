"""/historique, /progression, /saison, /palmares, /cloturer-saison."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..logging_conf import get_logger
from ..services.embeds import COLOUR_LIVE, COLOUR_LOSS, COLOUR_WIN, queue_name
from ..services.history import (
    bet_totals,
    guild_recent_games,
    player_form,
    recent_games,
)
from ..services.progression import (
    days_since,
    latest_snapshot,
    progression,
    snapshot_label,
    sparkline,
)
from ..services.registration import linked_players
from ..services.seasons import (
    SeasonError,
    close_season,
    current_season,
    ensure_season,
    hall_of_fame,
    past_seasons,
    standings_of,
)
from ..utils import format_ago, format_coins, format_duration, format_points

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)

MEDALS = ("\N{FIRST PLACE MEDAL}", "\N{SECOND PLACE MEDAL}", "\N{THIRD PLACE MEDAL}")
WIN_MARK = "\N{LARGE GREEN CIRCLE}"
LOSS_MARK = "\N{LARGE RED CIRCLE}"


def form_line(form) -> str:
    """Résumé d'une forme : bilan, série en cours, faits marquants."""
    if form.is_new:
        return "Aucune partie enregistrée pour l'instant."
    parts = [f"{form.wins}V / {form.losses}D sur {form.games} parties"]
    rate = form.winrate
    if rate is not None:
        parts[0] += f" ({rate:.0f}%)"
    if form.winning_streak >= 2:
        parts.append(f"\N{FIRE} {form.winning_streak} victoires d'affilée")
    elif form.losing_streak >= 2:
        parts.append(f"\N{DOWNWARDS BLACK ARROW} {form.losing_streak} défaites d'affilée")
    if form.mvp_count:
        parts.append(f"{form.mvp_count} MVP")
    if form.lvp_count:
        parts.append(f"{form.lvp_count} LVP")
    parts.append(f"KDA moyen {form.avg_kda:.2f}")
    return " • ".join(parts)


class Stats(commands.Cog):
    def __init__(self, bot: LoLBet) -> None:
        self.bot = bot

    async def _player_of(self, guild_id: int, discord_id: int):
        async with self.bot.session_factory() as session:
            players = await linked_players(session, guild_id)
        return next((p for p in players if p.discord_id == discord_id), None)

    # -- historique --------------------------------------------------------

    @app_commands.command(
        name="historique", description="Les dernières parties suivies et leurs paris."
    )
    @app_commands.describe(joueur="De qui voir l'historique. Tout le serveur si vide.")
    @app_commands.guild_only()
    async def history(
        self, interaction: discord.Interaction, joueur: discord.User | None = None
    ) -> None:
        guild_id = interaction.guild_id or 0

        async with self.bot.session_factory() as session:
            if joueur is None:
                games = await guild_recent_games(session, guild_id, limit=10)
                form = None
                totals = None
            else:
                games = await recent_games(session, guild_id, joueur.id, limit=10)
                form = await player_form(session, guild_id, joueur.id)
                totals = await bet_totals(session, guild_id, joueur.id)

        if not games:
            await interaction.response.send_message(
                "Aucune partie enregistrée. L'historique se remplit à la fin de "
                "chaque partie suivie.",
                ephemeral=True,
            )
            return

        lines = []
        for stat in games:
            mark = WIN_MARK if stat.win else LOSS_MARK
            awards = ""
            if stat.is_mvp:
                awards = " \N{GLOWING STAR}"
            elif stat.is_lvp:
                awards = " \N{POLICE CAR}"
            who = "" if joueur is not None else f"<@{stat.discord_id}> "
            lines.append(
                f"{mark} {who}`{stat.champion_name or stat.champion_id}` "
                f"**{stat.kda_line}**{awards} • {format_points(stat.damage)} dégâts • "
                f"{format_duration(stat.duration_seconds)} • {format_ago(stat.played_at)}"
            )

        title = (
            f"Historique - {joueur.display_name}"
            if joueur is not None
            else "Dernières parties du serveur"
        )
        embed = discord.Embed(
            title=title, description="\n".join(lines)[:4096], colour=COLOUR_LIVE
        )
        if form is not None:
            embed.add_field(name="Bilan", value=form_line(form), inline=False)
        if totals and totals["settled"]:
            embed.add_field(
                name="Paris réglés",
                value=(
                    f"{totals['settled']} paris • meilleur **{totals['best']:+,}** • "
                    f"pire **{totals['worst']:+,}**"
                ),
                inline=False,
            )
        embed.set_footer(text=f"{len(games)} dernières parties")
        await interaction.response.send_message(embed=embed)

    # -- progression -------------------------------------------------------

    @app_commands.command(
        name="progression", description="L'évolution du rang sur les derniers jours."
    )
    @app_commands.describe(
        joueur="De qui voir la progression. Toi par défaut.",
        jours="Fenêtre en jours (30 par défaut).",
    )
    @app_commands.guild_only()
    async def progression_command(
        self,
        interaction: discord.Interaction,
        joueur: discord.User | None = None,
        jours: int | None = None,
    ) -> None:
        target = joueur or interaction.user
        guild_id = interaction.guild_id or 0
        window = max(1, min(365, jours or 30))

        player = await self._player_of(guild_id, target.id)
        if player is None:
            await interaction.response.send_message(
                f"{target.mention} n'a pas de compte lié ici.", ephemeral=True
            )
            return

        async with self.bot.session_factory() as session:
            data = await progression(session, player.puuid, days=window)
            newest = data.last or await latest_snapshot(session, player.puuid)

        if newest is None:
            await interaction.response.send_message(
                "Aucun relevé de rang pour l'instant. Le premier est pris à la fin "
                "de la prochaine partie suivie.",
                ephemeral=True,
            )
            return

        delta = data.delta
        colour = COLOUR_WIN if delta > 0 else COLOUR_LOSS if delta < 0 else COLOUR_LIVE
        embed = discord.Embed(
            title=f"Progression - {player.riot_id}",
            colour=colour,
            description=f"Rang actuel : **{snapshot_label(newest)}**",
        )

        if data.first is not None and len(data.snapshots) > 1:
            sign = "+" if delta >= 0 else ""
            embed.add_field(
                name=f"Sur {window} jours",
                value=(
                    f"Départ : {snapshot_label(data.first)}\n"
                    f"Écart : **{sign}{delta}** points de ladder\n"
                    f"{sparkline(data.snapshots)}"
                ),
                inline=False,
            )
            embed.add_field(name="Relevés", value=str(len(data.snapshots)))
            embed.add_field(name="Après partie", value=str(data.games))
        else:
            embed.add_field(
                name=f"Sur {window} jours",
                value=(
                    "Pas encore assez de relevés pour tracer une évolution. "
                    "Un relevé est pris à chaque partie suivie, s'il a changé."
                ),
                inline=False,
            )

        age = days_since(newest)
        if age is not None:
            embed.set_footer(text=f"Dernier relevé il y a {age} jour(s)")
        await interaction.response.send_message(embed=embed)

    # -- saisons -----------------------------------------------------------

    @app_commands.command(name="saison", description="La saison en cours et son classement.")
    @app_commands.guild_only()
    async def season(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        async with self.bot.session_factory() as session:
            season = await ensure_season(
                session, guild_id, starting_balance=self.bot.settings.starting_balance
            )
            await session.commit()
            top = await self.bot.betting.leaderboard(session, guild_id, limit=5)
            titles = await hall_of_fame(session, guild_id)
            previous = await past_seasons(session, guild_id, limit=1)

        embed = discord.Embed(
            title=f"{season.name} - en cours",
            colour=COLOUR_LIVE,
            description=f"Ouverte {format_ago(season.started_at)}.",
        )
        if top:
            embed.add_field(
                name="Tête du classement",
                value="\n".join(
                    f"{MEDALS[i] if i < 3 else f'`{i + 1}.`'} <@{w.user_id}> - "
                    f"**{format_coins(w.balance)}**"
                    for i, w in enumerate(top)
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="Tête du classement", value="Personne n'a encore parié.", inline=False
            )
        if titles:
            embed.add_field(
                name="Titres remportés",
                value="\n".join(f"<@{uid}> - {count}" for uid, count in titles[:5]),
                inline=False,
            )
        if previous:
            embed.set_footer(text=f"Saison précédente : {previous[0].name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="palmares", description="Le classement figé des saisons terminées."
    )
    @app_commands.guild_only()
    async def hall(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        async with self.bot.session_factory() as session:
            seasons = await past_seasons(session, guild_id, limit=5)
            blocks = [
                (season, await standings_of(session, int(season.id or 0), limit=5))
                for season in seasons
            ]

        if not blocks:
            await interaction.response.send_message(
                "Aucune saison terminée. Le palmarès se remplit avec "
                "`/cloturer-saison`.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title="Palmarès", colour=discord.Colour(0xF1C40F))
        for season, standings in blocks:
            value = "\n".join(
                f"{MEDALS[s.position - 1] if s.position <= 3 else f'`{s.position}.`'} "
                f"<@{s.user_id}> - **{format_coins(s.balance)}** "
                f"({s.bets_won}V/{s.bets_lost}D)"
                for s in standings
            )
            embed.add_field(
                name=f"{season.name} - close {format_ago(season.ended_at)}",
                value=value or "Aucun participant",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="cloturer-saison",
        description="Fige le classement, archive la saison et remet les soldes à zéro.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def close(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        async with self.bot.session_factory() as session:
            await ensure_season(
                session, guild_id, starting_balance=self.bot.settings.starting_balance
            )
            try:
                closed = await close_season(
                    session,
                    guild_id,
                    starting_balance=self.bot.settings.starting_balance,
                )
            except SeasonError as exc:
                await session.rollback()
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            await session.commit()
            new_season = await current_season(session, guild_id)

        champion = closed.champion
        embed = discord.Embed(
            title=f"\N{TROPHY} {closed.season.name} terminée",
            colour=discord.Colour(0xF1C40F),
            description=(
                f"Vainqueur : <@{champion.user_id}> avec "
                f"**{format_coins(champion.balance)}** pièces."
                if champion
                else "Aucun participant."
            ),
        )
        embed.add_field(
            name="Classement final",
            value="\n".join(
                f"{MEDALS[s.position - 1] if s.position <= 3 else f'`{s.position}.`'} "
                f"<@{s.user_id}> - **{format_coins(s.balance)}** "
                f"({s.bets_won}V/{s.bets_lost}D, {s.net_profit:+,})"
                for s in closed.standings[:10]
            )
            or "-",
            inline=False,
        )
        if new_season is not None:
            embed.set_footer(
                text=(
                    f"{new_season.name} ouverte - tout le monde repart à "
                    f"{self.bot.settings.starting_balance} pièces. "
                    "L'historique des parties est conservé."
                )
            )
        log.info("season.closed", guild=guild_id, season=closed.season.number)
        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Cette commande est réservée aux gestionnaires du serveur.", ephemeral=True
            )
            return
        log.exception("stats.command_failed", error=str(error))
        if not interaction.response.is_done():
            await interaction.response.send_message("Ça n'a pas fonctionné.", ephemeral=True)


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Stats(bot))
