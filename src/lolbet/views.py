"""Buttons and the bet-amount modal.

These are :class:`discord.ui.DynamicItem` components, so their custom_id
carries the game id. That means a restarted bot can serve buttons on messages
it posted days ago without keeping any view objects alive.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord

from .logging_conf import get_logger
from .models import BetSide, GameStatus, TrackedGame
from .services.betting import BettingError
from .utils import format_coins

if TYPE_CHECKING:  # pragma: no cover
    from .bot import LoLBet

log = get_logger(__name__)

BET_PATTERN = r"lolbet:bet:(?P<game>[0-9]+):(?P<side>WIN|LOSS)"
CANCEL_PATTERN = r"lolbet:cancel:(?P<game>[0-9]+)"


class AmountError(ValueError):
    """Raised when the modal input cannot be read as a number of coins."""


def parse_amount(raw: str, balance: int) -> int:
    """Read a bet amount. Accepts 250, 2k, 50%, half, all.

    Pure function so the parsing rules are unit-testable without Discord.
    """
    text = (raw or "").strip().lower().replace(" ", "").replace(",", "").replace("_", "")
    if not text:
        raise AmountError("Enter an amount.")

    if text in ("all", "max", "allin", "all-in"):
        return balance
    if text == "half":
        return balance // 2

    if text.endswith("%"):
        try:
            percent = float(text[:-1])
        except ValueError as exc:
            raise AmountError(f"{raw!r} is not a percentage.") from exc
        if not 0 < percent <= 100:
            raise AmountError("Use a percentage between 0 and 100.")
        return int(balance * percent / 100)

    multiplier = 1
    if text.endswith("k"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000, text[:-1]

    try:
        value = float(text) * multiplier
    except ValueError as exc:
        raise AmountError(f"{raw!r} is not a number.") from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise AmountError("That is not a usable amount.")
    return int(value)


async def _load_game(bot: LoLBet, game_id: int) -> TrackedGame | None:
    async with bot.session_factory() as session:
        return await session.get(TrackedGame, game_id)


class BetAmountModal(discord.ui.Modal):
    amount: discord.ui.TextInput = discord.ui.TextInput(
        label="Amount (coins)",
        placeholder="250, 2k, 50% or all",
        required=True,
        max_length=16,
    )

    def __init__(self, game_id: int, side: str, balance: int) -> None:
        super().__init__(title=f"Bet {side} - balance {format_coins(balance)}"[:45])
        self.game_id = game_id
        self.side = side
        self.balance = balance

    async def on_submit(self, interaction: discord.Interaction) -> None:
        bot: LoLBet = interaction.client  # type: ignore[assignment]
        try:
            amount = parse_amount(str(self.amount.value), self.balance)
        except AmountError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, self.game_id)
            if game is None:
                await interaction.response.send_message(
                    "That game is no longer tracked.", ephemeral=True
                )
                return
            try:
                bet, wallet = await bot.betting.place_bet(
                    session, game, interaction.user.id, self.side, amount
                )
            except BettingError as exc:
                await session.rollback()
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            await session.commit()
            pool = await bot.betting.pool(session, self.game_id)

        multiplier = pool.multiplier(self.side)
        odds = f" at ~x{multiplier:.2f}" if multiplier else ""
        await interaction.response.send_message(
            f"Bet placed: **{format_coins(bet.amount)}** on **{self.side}**{odds}.\n"
            f"Balance: {format_coins(wallet.balance)} coins. "
            "Use `/cancelbet` before the lock if you change your mind.",
            ephemeral=True,
        )
        bot.updater.schedule(self.game_id)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:  # pragma: no cover - defensive
        log.exception("modal.failed", error=str(error))
        message = "Something broke while placing that bet. Nothing was charged."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class BetButton(discord.ui.DynamicItem[discord.ui.Button], template=BET_PATTERN):
    def __init__(self, game_id: int, side: str) -> None:
        self.game_id = game_id
        self.side = side
        win = side == BetSide.WIN
        super().__init__(
            discord.ui.Button(
                label=f"Bet {side}",
                style=discord.ButtonStyle.success if win else discord.ButtonStyle.danger,
                custom_id=f"lolbet:bet:{game_id}:{side}",
                emoji="\N{CHART WITH UPWARDS TREND}" if win else "\N{CHART WITH DOWNWARDS TREND}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> BetButton:
        return cls(int(match["game"]), match["side"])

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: LoLBet = interaction.client  # type: ignore[assignment]
        game = await _load_game(bot, self.game_id)
        if game is None:
            await interaction.response.send_message(
                "That game is no longer tracked.", ephemeral=True
            )
            return
        if not bot.betting.is_open(game):
            await interaction.response.send_message(
                "Betting is locked for this game.", ephemeral=True
            )
            return

        async with bot.session_factory() as session:
            wallet = await bot.betting.get_wallet(session, game.guild_id, interaction.user.id)
            await session.commit()

        if wallet.balance < bot.settings.min_bet:
            await interaction.response.send_message(
                f"You are out of coins ({format_coins(wallet.balance)}). Try `/daily`.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            BetAmountModal(self.game_id, self.side, wallet.balance)
        )


class CancelBetButton(discord.ui.DynamicItem[discord.ui.Button], template=CANCEL_PATTERN):
    def __init__(self, game_id: int) -> None:
        self.game_id = game_id
        super().__init__(
            discord.ui.Button(
                label="Cancel bet",
                style=discord.ButtonStyle.secondary,
                custom_id=f"lolbet:cancel:{game_id}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> CancelBetButton:
        return cls(int(match["game"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: LoLBet = interaction.client  # type: ignore[assignment]
        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, self.game_id)
            if game is None:
                await interaction.response.send_message(
                    "That game is no longer tracked.", ephemeral=True
                )
                return
            try:
                bet, wallet = await bot.betting.cancel_bet(session, game, interaction.user.id)
            except BettingError as exc:
                await session.rollback()
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            await session.commit()

        await interaction.response.send_message(
            f"Cancelled your {format_coins(bet.amount)} coin bet on **{bet.side}**. "
            f"Balance: {format_coins(wallet.balance)}.",
            ephemeral=True,
        )
        bot.updater.schedule(self.game_id)


class BetView(discord.ui.View):
    """The three buttons attached to a live-game announcement."""

    def __init__(self, game_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(BetButton(game_id, BetSide.WIN))
        self.add_item(BetButton(game_id, BetSide.LOSS))
        self.add_item(CancelBetButton(game_id))


def view_for(game: TrackedGame) -> BetView | None:
    """Buttons while bets are open, nothing once the game is locked."""
    if game.status != GameStatus.LIVE or game.id is None:
        return None
    return BetView(game.id)
