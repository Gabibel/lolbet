"""/solde, /quotidien, /paris, /annulerpari."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from ..logging_conf import get_logger
from ..models import Bet, GameStatus, TrackedGame
from ..services.betting import BettingError
from ..services.embeds import queue_name
from ..utils import discord_timestamp, format_coins, format_duration
from ..views import SIDE_LABELS

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)


class Betting(commands.Cog):
    def __init__(self, bot: LoLBet) -> None:
        self.bot = bot

    async def _open_bets(self, guild_id: int, user_id: int) -> list[tuple[Bet, TrackedGame]]:
        async with self.bot.session_factory() as session:
            rows = (
                await session.execute(
                    select(Bet, TrackedGame)
                    .join(TrackedGame, TrackedGame.id == Bet.game_id)
                    .where(
                        Bet.user_id == user_id,
                        Bet.guild_id == guild_id,
                        TrackedGame.status == GameStatus.LIVE,
                    )
                    .order_by(Bet.created_at.desc())
                )
            ).all()
        return [(bet, game) for bet, game in rows]

    @app_commands.command(name="solde", description="Ton solde de pièces sur ce serveur.")
    @app_commands.describe(user="De qui afficher le solde. Toi par défaut.")
    @app_commands.guild_only()
    async def balance(
        self, interaction: discord.Interaction, user: discord.User | None = None
    ) -> None:
        target = user or interaction.user
        async with self.bot.session_factory() as session:
            wallet = await self.bot.betting.get_wallet(
                session, interaction.guild_id or 0, target.id, create=False
            )
        await interaction.response.send_message(
            f"{target.mention} a **{format_coins(wallet.balance)}** pièces "
            f"({wallet.bets_won}V/{wallet.bets_lost}D, net {wallet.net_profit:+,}).",
            ephemeral=True,
        )

    @app_commands.command(name="quotidien", description="Réclame tes pièces du jour.")
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction) -> None:
        async with self.bot.session_factory() as session:
            amount, remaining = await self.bot.betting.claim_daily(
                session, interaction.guild_id or 0, interaction.user.id
            )
            wallet = await self.bot.betting.get_wallet(
                session, interaction.guild_id or 0, interaction.user.id
            )
            await session.commit()

        if amount == 0 and remaining is not None:
            await interaction.response.send_message(
                f"Déjà réclamé. Prochaine fois dans "
                f"**{format_duration(remaining.total_seconds())}**.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"**+{format_coins(amount)}** pièces. Solde : "
            f"**{format_coins(wallet.balance)}**.",
            ephemeral=True,
        )

    @app_commands.command(name="paris", description="Tes paris en cours sur ce serveur.")
    @app_commands.guild_only()
    async def bets(self, interaction: discord.Interaction) -> None:
        open_bets = await self._open_bets(interaction.guild_id or 0, interaction.user.id)
        if not open_bets:
            await interaction.response.send_message(
                "Aucun pari en cours. Ils se placent sur les boutons des annonces de partie.",
                ephemeral=True,
            )
            return

        lines = []
        for bet, game in open_bets:
            lock = discord_timestamp(game.lock_at) if game.lock_at else "bientôt"
            lines.append(
                f"**{SIDE_LABELS.get(bet.side, bet.side)}** {format_coins(bet.amount)} sur "
                f"`{game.riot_game_id}` ({queue_name(game.queue_id)}) - fermeture {lock}"
            )
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    async def game_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        open_bets = await self._open_bets(interaction.guild_id or 0, interaction.user.id)
        current = (current or "").lower()
        return [
            app_commands.Choice(
                name=f"{game.riot_game_id} - {SIDE_LABELS.get(bet.side, bet.side)} "
                f"{bet.amount}"[:100],
                value=str(game.id),
            )
            for bet, game in open_bets
            if current in game.riot_game_id.lower()
        ][:25]

    @app_commands.command(
        name="annulerpari", description="Annule un pari avant la fermeture des paris."
    )
    @app_commands.describe(game="Quel pari annuler. Utile seulement si tu en as plusieurs.")
    @app_commands.autocomplete(game=game_autocomplete)
    @app_commands.guild_only()
    async def cancelbet(
        self, interaction: discord.Interaction, game: str | None = None
    ) -> None:
        open_bets = await self._open_bets(interaction.guild_id or 0, interaction.user.id)
        if not open_bets:
            await interaction.response.send_message(
                "Aucun pari annulable. Les paris se ferment 5 minutes après le début "
                "de la partie.",
                ephemeral=True,
            )
            return

        if game is not None:
            try:
                wanted = int(game)
            except ValueError:
                wanted = -1
            chosen = next((pair for pair in open_bets if pair[1].id == wanted), None)
            if chosen is None:
                await interaction.response.send_message(
                    "Aucun pari en cours sur cette partie.", ephemeral=True
                )
                return
        elif len(open_bets) > 1:
            listing = "\n".join(
                f"- `{g.riot_game_id}` ({SIDE_LABELS.get(b.side, b.side)} "
                f"{format_coins(b.amount)})"
                for b, g in open_bets
            )
            await interaction.response.send_message(
                f"Tu as plusieurs paris en cours. Relance `/annulerpari` et choisis :\n"
                f"{listing}",
                ephemeral=True,
            )
            return
        else:
            chosen = open_bets[0]

        _, tracked_game = chosen
        async with self.bot.session_factory() as session:
            stored = await session.get(TrackedGame, tracked_game.id)
            if stored is None:
                await interaction.response.send_message(
                    "Cette partie n'est plus suivie.", ephemeral=True
                )
                return
            try:
                bet, wallet = await self.bot.betting.cancel_bet(
                    session, stored, interaction.user.id
                )
            except BettingError as exc:
                await session.rollback()
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            await session.commit()

        await interaction.response.send_message(
            f"**{format_coins(bet.amount)}** sur **{SIDE_LABELS.get(bet.side, bet.side)}** "
            f"annulé. Solde : {format_coins(wallet.balance)}.",
            ephemeral=True,
        )
        if tracked_game.id is not None:
            self.bot.updater.schedule(tracked_game.id)


async def setup(bot: LoLBet) -> None:
    await bot.add_cog(Betting(bot))
