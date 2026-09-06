"""Boutons et fenêtre de saisie du montant.

Ce sont des :class:`discord.ui.DynamicItem` : l'identifiant de la partie est
porté par le custom_id, donc un bot redémarré sait encore répondre aux boutons
de messages postés il y a plusieurs jours.
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

SIDE_LABELS = {BetSide.WIN: "VICTOIRE", BetSide.LOSS: "DÉFAITE"}

ALL_IN_WORDS = frozenset({"tout", "all", "max", "allin", "all-in", "tapis"})
HALF_WORDS = frozenset({"moitie", "moitié", "half", "demi"})


class AmountError(ValueError):
    """Le montant saisi dans la fenêtre est illisible."""


def parse_amount(raw: str, balance: int) -> int:
    """Lit un montant de pari. Accepte 250, 2k, 50%, moitié, tout.

    Fonction pure : les règles de saisie sont testables sans Discord.
    """
    text = (raw or "").strip().lower().replace(" ", "").replace(",", "").replace("_", "")
    if not text:
        raise AmountError("Indique un montant.")

    if text in ALL_IN_WORDS:
        return balance
    if text in HALF_WORDS:
        return balance // 2

    if text.endswith("%"):
        try:
            percent = float(text[:-1])
        except ValueError as exc:
            raise AmountError(f"« {raw} » n'est pas un pourcentage.") from exc
        if not 0 < percent <= 100:
            raise AmountError("Utilise un pourcentage entre 0 et 100.")
        return int(balance * percent / 100)

    multiplier = 1
    if text.endswith("k"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000, text[:-1]

    try:
        value = float(text) * multiplier
    except ValueError as exc:
        raise AmountError(f"« {raw} » n'est pas un nombre.") from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise AmountError("Ce montant est inutilisable.")
    return int(value)


async def _load_game(bot: LoLBet, game_id: int) -> TrackedGame | None:
    async with bot.session_factory() as session:
        return await session.get(TrackedGame, game_id)


class BetAmountModal(discord.ui.Modal):
    amount: discord.ui.TextInput = discord.ui.TextInput(
        label="Montant (pièces)",
        placeholder="250, 2k, 50% ou tout",
        required=True,
        max_length=16,
    )

    def __init__(self, game_id: int, side: str, balance: int) -> None:
        super().__init__(title=f"Parier {SIDE_LABELS[side]} - {format_coins(balance)}"[:45])
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
                    "Cette partie n'est plus suivie.", ephemeral=True
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
        odds = f" à ~x{multiplier:.2f}" if multiplier else ""
        await interaction.response.send_message(
            f"Pari enregistré : **{format_coins(bet.amount)}** sur "
            f"**{SIDE_LABELS[self.side]}**{odds}.\n"
            f"Solde : {format_coins(wallet.balance)} pièces. "
            "Tu peux encore utiliser `/annulerpari` avant la fermeture.",
            ephemeral=True,
        )
        bot.updater.schedule(self.game_id)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:  # pragma: no cover - defensive
        log.exception("modal.failed", error=str(error))
        message = "Quelque chose a cassé pendant le pari. Rien n'a été débité."
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
                label=f"Parier {SIDE_LABELS[side]}",
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
                "Cette partie n'est plus suivie.", ephemeral=True
            )
            return
        if not bot.betting.is_open(game):
            await interaction.response.send_message(
                "Les paris sont fermés pour cette partie.", ephemeral=True
            )
            return

        async with bot.session_factory() as session:
            wallet = await bot.betting.get_wallet(session, game.guild_id, interaction.user.id)
            await session.commit()

        if wallet.balance < bot.settings.min_bet:
            await interaction.response.send_message(
                f"Tu n'as plus de pièces ({format_coins(wallet.balance)}). "
                "Essaie `/quotidien`.",
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
                label="Annuler mon pari",
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
                    "Cette partie n'est plus suivie.", ephemeral=True
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
            f"Pari de {format_coins(bet.amount)} pièces sur "
            f"**{SIDE_LABELS.get(bet.side, bet.side)}** annulé. "
            f"Solde : {format_coins(wallet.balance)}.",
            ephemeral=True,
        )
        bot.updater.schedule(self.game_id)


class BetView(discord.ui.View):
    """Les trois boutons attachés à une annonce de partie en cours."""

    def __init__(self, game_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(BetButton(game_id, BetSide.WIN))
        self.add_item(BetButton(game_id, BetSide.LOSS))
        self.add_item(CancelBetButton(game_id))


def view_for(game: TrackedGame) -> BetView | None:
    """Les boutons tant que les paris sont ouverts, plus rien ensuite."""
    if game.status != GameStatus.LIVE or game.id is None:
        return None
    return BetView(game.id)
