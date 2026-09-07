"""/pari-morts et /cotes-morts : le marché annexe.

Une partie déséquilibrée n'a plus d'intérêt sur le marché principal — tout le
monde voit qui va gagner. Parier sur le nombre de morts de quelqu'un reste
ouvert quel que soit le pronostic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from ..logging_conf import get_logger
from ..models import GameStatus, PropPick, TrackedGame, TrackedParticipant
from ..services.betting import BettingError
from ..services.embeds import queue_name
from ..services.props import PropError, describe
from ..utils import discord_timestamp, format_coins

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)

PICKS = [
    app_commands.Choice(name="PLUS de morts que la ligne", value=PropPick.OVER.value),
    app_commands.Choice(name="MOINS de morts que la ligne", value=PropPick.UNDER.value),
]


class Props(commands.Cog):
    def __init__(self, bot: LoLBet) -> None:
        self.bot = bot

    async def _live_game(self, guild_id: int) -> TrackedGame | None:
        """La partie en cours sur laquelle on peut encore parier."""
        async with self.bot.session_factory() as session:
            return (
                await session.execute(
                    select(TrackedGame)
                    .where(
                        TrackedGame.guild_id == guild_id,
                        TrackedGame.status == GameStatus.LIVE,
                    )
                    .order_by(TrackedGame.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

    async def target_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        game = await self._live_game(interaction.guild_id or 0)
        if game is None:
            return []
        async with self.bot.session_factory() as session:
            participants = list(
                (
                    await session.execute(
                        select(TrackedParticipant).where(
                            TrackedParticipant.game_id == game.id
                        )
                    )
                )
                .scalars()
                .all()
            )
        current = (current or "").lower()
        return [
            app_commands.Choice(name=p.riot_id[:100], value=p.puuid)
            for p in participants
            if current in p.riot_id.lower()
        ][:25]

    @app_commands.command(
        name="cotes-morts",
        description="Les lignes de morts ouvertes sur la partie en cours.",
    )
    @app_commands.guild_only()
    async def lines(self, interaction: discord.Interaction) -> None:
        game = await self._live_game(interaction.guild_id or 0)
        if game is None:
            await interaction.response.send_message(
                "Aucune partie en cours pour l'instant.", ephemeral=True
            )
            return

        async with self.bot.session_factory() as session:
            lines = await self.bot.props.lines_for(session, game)

        if not lines:
            await interaction.response.send_message(
                "Aucun joueur suivi dans cette partie.", ephemeral=True
            )
            return

        lock = discord_timestamp(game.lock_at) if game.lock_at else "bientôt"
        rendered = [
            f"**{line.target_name}** \N{EM DASH} ligne à **{line.line:g}** morts\n"
            f"   PLUS ×{line.pool.over_odds:.2f} \N{BULLET} "
            f"MOINS ×{line.pool.under_odds:.2f}"
            + (f" \N{BULLET} {format_coins(line.pool.total)} misées" if line.pool.total else "")
            for line in lines
        ]
        await interaction.response.send_message(
            f"`{game.riot_game_id}` ({queue_name(game.queue_id)}) \N{BULLET} "
            f"fermeture {lock}\n\n" + "\n".join(rendered)
            + "\n\nPour miser : `/pari-morts`. La ligne est en demi-point, "
            "il n'y a donc jamais d'égalité.",
            ephemeral=True,
        )

    @app_commands.command(
        name="pari-morts",
        description="Parie sur le nombre de morts d'un joueur de la partie en cours.",
    )
    @app_commands.describe(
        joueur="Sur qui parier",
        pari="Plus ou moins de morts que la ligne",
        montant="Combien de pièces miser",
    )
    @app_commands.autocomplete(joueur=target_autocomplete)
    @app_commands.choices(pari=PICKS)
    @app_commands.guild_only()
    async def place(
        self,
        interaction: discord.Interaction,
        joueur: str,
        pari: app_commands.Choice[str],
        montant: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        game = await self._live_game(interaction.guild_id or 0)
        if game is None:
            await interaction.response.send_message(
                "Aucune partie en cours pour l'instant.", ephemeral=True
            )
            return

        try:
            async with self.bot.session_factory() as session:
                bet, wallet = await self.bot.props.place(
                    session,
                    game,
                    interaction.user.id,
                    joueur,
                    pari.value,
                    montant,
                )
                await session.commit()
                summary = describe(bet)
                odds, amount, balance = bet.odds, bet.amount, wallet.balance
        except (BettingError, PropError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        gain = int(amount * odds)
        await interaction.response.send_message(
            f"Pari pris : **{summary}**\n"
            f"{format_coins(amount)} pièces à la cote **×{odds:.2f}** "
            f"\N{EM DASH} {format_coins(gain)} si ça passe.\n"
            f"Il te reste {format_coins(balance)} pièces.",
            ephemeral=True,
        )

    @app_commands.command(
        name="annuler-pari-morts",
        description="Annule un pari sur les morts, tant que la partie n'est pas verrouillée.",
    )
    @app_commands.describe(joueur="Le pari à annuler")
    @app_commands.autocomplete(joueur=target_autocomplete)
    @app_commands.guild_only()
    async def cancel(self, interaction: discord.Interaction, joueur: str) -> None:
        game = await self._live_game(interaction.guild_id or 0)
        if game is None:
            await interaction.response.send_message(
                "Aucune partie en cours pour l'instant.", ephemeral=True
            )
            return
        try:
            async with self.bot.session_factory() as session:
                bet = await self.bot.props.cancel(
                    session, game, interaction.user.id, joueur
                )
                await session.commit()
                summary = describe(bet)
                amount = bet.amount
        except (BettingError, PropError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            f"Pari annulé : **{summary}**. {format_coins(amount)} pièces rendues.",
            ephemeral=True,
        )

    @app_commands.command(
        name="mes-paris-morts",
        description="Tes paris annexes encore en cours.",
    )
    @app_commands.guild_only()
    async def mine(self, interaction: discord.Interaction) -> None:
        async with self.bot.session_factory() as session:
            bets = await self.bot.props.open_bets_for(
                session, interaction.guild_id or 0, interaction.user.id
            )
        if not bets:
            await interaction.response.send_message(
                "Aucun pari annexe en cours. `/cotes-morts` pour voir les lignes.",
                ephemeral=True,
            )
            return
        lines = [
            f"**{describe(bet)}** \N{EM DASH} {format_coins(bet.amount)} pièces "
            f"à ×{bet.odds:.2f}"
            for bet in bets
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        log.exception("props.command_failed", error=str(error))
        if not interaction.response.is_done():
            await interaction.response.send_message("Ça n'a pas fonctionné.", ephemeral=True)


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Props(bot))
