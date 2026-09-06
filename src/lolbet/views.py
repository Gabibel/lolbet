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
from .services.betting import BettingError, Pool
from .services.embeds import SideLabels, side_labels_for
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
        participants = await _tracked_participants(bot, self.game_id)
        labels = side_labels_for(participants, game.tracked_team_id)

        multiplier = pool.multiplier(self.side)
        odds = f" à ~x{multiplier:.2f}" if multiplier else ""
        await interaction.response.send_message(
            f"Pari enregistré : **{format_coins(bet.amount)}** sur "
            f"**{labels.of(self.side)}**{odds}.\n"
            f"Solde : {format_coins(wallet.balance)} pièces. {COMMANDS_HELP}",
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
    def __init__(self, game_id: int, side: str, label: str | None = None) -> None:
        self.game_id = game_id
        self.side = side
        win = side == BetSide.WIN
        # Le libellé affiché est celui du message déjà posté ; celui-ci ne
        # sert qu'à reconstruire le bouton après un redémarrage.
        text = label or SIDE_LABELS[side]
        super().__init__(
            discord.ui.Button(
                label=f"Parier {text}"[:80],
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

        async with bot.session_factory() as session:
            pool = await bot.betting.pool(session, self.game_id)
            participants = await _tracked_participants(bot, self.game_id)
        labels = side_labels_for(participants, game.tracked_team_id)

        await interaction.response.send_message(
            content=bet_panel_text(self.side, wallet.balance, pool, labels),
            view=BetPanelView(self.game_id, self.side, wallet.balance),
            ephemeral=True,
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


QUICK_AMOUNTS = (100, 250, 500, 1000)

COMMANDS_HELP = (
    "`/solde` ton solde • `/quotidien` +100 par jour • "
    "`/paris` tes paris en cours • `/annulerpari` annuler avant la fermeture"
)


async def _tracked_participants(bot: LoLBet, game_id: int) -> list:
    """Les inscrits présents dans cette partie, pour nommer les deux camps."""
    from sqlalchemy import select

    from .models import TrackedParticipant

    async with bot.session_factory() as session:
        rows = await session.execute(
            select(TrackedParticipant).where(TrackedParticipant.game_id == game_id)
        )
        return list(rows.scalars().all())


def bet_panel_text(
    side: str, balance: int, pool: Pool, labels: SideLabels | None = None
) -> str:
    """Ce que le joueur voit après avoir cliqué sur Parier."""
    labels = labels or SideLabels()
    multiplier = pool.multiplier(side)
    odds = f"cote actuelle **x{multiplier:.2f}**" if multiplier else "personne n'a encore parié de ce côté"
    lines = [
        f"\N{MONEY BAG} Ton solde : **{format_coins(balance)}** pièces",
        f"Tu paries sur **{labels.of(side)}** - {odds}.",
    ]
    if pool.count:
        lines.append(
            f"Cagnotte : **{pool.total:,}** pièces "
            f"({labels.win} {pool.win_amount:,} / {labels.loss} {pool.loss_amount:,})"
        )
    if balance <= 0:
        lines.append("Tu n'as plus rien à miser. `/quotidien` te redonne 100 pièces.")
    else:
        lines.append("Choisis un montant ci-dessous, ou saisis-le toi-même.")
    lines.append(f"\n{COMMANDS_HELP}")
    return "\n".join(lines)


class QuickBetButton(discord.ui.Button):
    """Un montant prêt à cliquer dans le panneau éphémère."""

    def __init__(self, game_id: int, side: str, amount: int, label: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.game_id = game_id
        self.side = side
        self.amount = amount

    async def callback(self, interaction: discord.Interaction) -> None:
        await _place_and_confirm(interaction, self.game_id, self.side, self.amount)


class CustomAmountButton(discord.ui.Button):
    def __init__(self, game_id: int, side: str, balance: int) -> None:
        super().__init__(label="Montant libre...", style=discord.ButtonStyle.secondary)
        self.game_id = game_id
        self.side = side
        self.balance = balance

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            BetAmountModal(self.game_id, self.side, self.balance)
        )


class BetPanelView(discord.ui.View):
    """Panneau éphémère : montants rapides + saisie libre.

    Éphémère et propre à une interaction, donc pas besoin de DynamicItem :
    il disparaît de lui-même et n'a pas à survivre à un redémarrage.
    """

    def __init__(self, game_id: int, side: str, balance: int) -> None:
        super().__init__(timeout=120)
        for amount in QUICK_AMOUNTS:
            if amount <= balance:
                self.add_item(
                    QuickBetButton(game_id, side, amount, format_coins(amount))
                )
        if balance > 0:
            self.add_item(
                QuickBetButton(game_id, side, balance, f"Tout ({format_coins(balance)})")
            )
        self.add_item(CustomAmountButton(game_id, side, balance))


async def _place_and_confirm(
    interaction: discord.Interaction, game_id: int, side: str, amount: int
) -> None:
    """Enregistre le pari et remplace le panneau par la confirmation."""
    bot: LoLBet = interaction.client  # type: ignore[assignment]
    async with bot.session_factory() as session:
        game = await session.get(TrackedGame, game_id)
        if game is None:
            await interaction.response.edit_message(
                content="Cette partie n'est plus suivie.", view=None
            )
            return
        try:
            bet, wallet = await bot.betting.place_bet(
                session, game, interaction.user.id, side, amount
            )
        except BettingError as exc:
            await session.rollback()
            await interaction.response.edit_message(content=str(exc), view=None)
            return
        await session.commit()
        pool = await bot.betting.pool(session, game_id)
        participants = await _tracked_participants(bot, game_id)

    labels = side_labels_for(participants, game.tracked_team_id)
    multiplier = pool.multiplier(side)
    odds = f" à ~x{multiplier:.2f}" if multiplier else ""
    await interaction.response.edit_message(
        content=(
            f"Pari enregistré : **{format_coins(bet.amount)}** sur "
            f"**{labels.of(side)}**{odds}.\n"
            f"Solde : {format_coins(wallet.balance)} pièces. {COMMANDS_HELP}"
        ),
        view=None,
    )
    bot.updater.schedule(game_id)


class BetView(discord.ui.View):
    """Les trois boutons attachés à une annonce de partie en cours."""

    def __init__(self, game_id: int, labels: SideLabels | None = None) -> None:
        super().__init__(timeout=None)
        labels = labels or SideLabels()
        self.add_item(BetButton(game_id, BetSide.WIN, labels.win))
        self.add_item(BetButton(game_id, BetSide.LOSS, labels.loss))
        self.add_item(CancelBetButton(game_id))


def view_for(game: TrackedGame, labels: SideLabels | None = None) -> BetView | None:
    """Les boutons tant que les paris sont ouverts, plus rien ensuite."""
    if game.status != GameStatus.LIVE or game.id is None:
        return None
    return BetView(game.id, labels)
