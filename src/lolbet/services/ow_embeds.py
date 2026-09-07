"""Les messages Overwatch : annonce de changement de rang, et profil.

Séparé de ``embeds.py`` parce que rien n'est partagé : pas de pool de paris,
pas de statistiques de partie, pas de MVP. Overwatch ne donne qu'un rang par
rôle, et ces messages ne prétendent pas en montrer plus.
"""

from __future__ import annotations

from datetime import datetime

import discord

from ..models import OverwatchPlayer, OverwatchRankSnapshot
from ..overwatch.rank import ROLES, UNRANKED_LABEL, OwRank
from ..utils import format_ago
from .overwatch import RoleChange, rank_of

COLOUR_UP = discord.Colour(0x2ECC71)
COLOUR_DOWN = discord.Colour(0xE74C3C)
COLOUR_NEUTRAL = discord.Colour(0xF99E1A)  # l'orange Overwatch

FOOTER_SOURCE = "Profil public Overwatch via OverFast"


def _colour_for(changes: list[RoleChange]) -> discord.Colour:
    """Vert si ça monte dans l'ensemble, rouge si ça descend."""
    total = sum(change.steps for change in changes)
    if total > 0:
        return COLOUR_UP
    if total < 0:
        return COLOUR_DOWN
    return COLOUR_NEUTRAL


def _title_for(changes: list[RoleChange]) -> str:
    if any(change.category == "promoted" for change in changes):
        return "\N{CHART WITH UPWARDS TREND} Promotion"
    if any(change.category == "demoted" for change in changes):
        return "\N{CHART WITH DOWNWARDS TREND} Rétrogradation"
    if all(change.category == "placed" for change in changes):
        return "\N{DIRECT HIT} Nouveau rang suivi"
    return "\N{LEFT RIGHT ARROW} Changement de rang"


def build_ow_change_embed(
    player: OverwatchPlayer,
    changes: list[RoleChange],
    *,
    ranks: dict[str, OwRank] | None = None,
    season: int | None = None,
) -> discord.Embed:
    """Ce qui a bougé, et où en est le reste des rôles."""
    embed = discord.Embed(
        title=_title_for(changes),
        colour=_colour_for(changes),
        description="\n".join(change.line for change in changes),
    )
    embed.set_author(name=player.username or player.battletag)
    if player.avatar_url:
        embed.set_thumbnail(url=player.avatar_url)

    others = {
        role: rank
        for role, rank in (ranks or {}).items()
        if role not in {change.role for change in changes}
    }
    if others:
        embed.add_field(
            name="Autres rôles",
            value="\n".join(others[role].display for role in ROLES if role in others),
            inline=False,
        )

    footer = FOOTER_SOURCE
    if season:
        footer = f"Saison {season} \N{BULLET} {footer}"
    embed.set_footer(text=footer)
    return embed


def build_ow_profile_embed(
    player: OverwatchPlayer,
    ranks: dict[str, OwRank],
    *,
    peaks: dict[str, OverwatchRankSnapshot] | None = None,
    last_move: OverwatchRankSnapshot | None = None,
    checked_at: datetime | None = None,
) -> discord.Embed:
    """Le profil : un rang par rôle, le sommet atteint, la dernière bougeotte."""
    embed = discord.Embed(
        title=player.username or player.battletag,
        colour=COLOUR_NEUTRAL,
        description=f"`{player.battletag}` \N{BULLET} {_platform_label(player.platform)}",
    )
    if player.avatar_url:
        embed.set_thumbnail(url=player.avatar_url)

    if ranks:
        embed.add_field(
            name="Rangs compétitifs",
            value="\n".join(ranks[role].display for role in ROLES if role in ranks),
            inline=False,
        )
    else:
        embed.add_field(
            name="Rangs compétitifs",
            value=(
                f"{UNRANKED_LABEL}. Soit les placements ne sont pas faits, soit "
                "le profil de carrière est en privé."
            ),
            inline=False,
        )

    peaks = peaks or {}
    tops = [
        f"{rank_of(snapshot).display}"
        for role in ROLES
        if (snapshot := peaks.get(role)) is not None
    ]
    if tops:
        embed.add_field(name="Meilleur relevé", value="\n".join(tops), inline=False)

    if last_move is not None:
        embed.add_field(
            name="Dernier changement",
            value=(
                f"{rank_of(last_move).display} \N{BULLET} "
                f"{format_ago(last_move.captured_at)}"
            ),
            inline=False,
        )

    footer = FOOTER_SOURCE
    if checked_at is not None:
        footer = f"Relevé {format_ago(checked_at)} \N{BULLET} {footer}"
    embed.set_footer(text=footer)
    return embed


def build_ow_roster_embed(
    entries: list[tuple[OverwatchPlayer, dict[str, OwRank]]],
) -> discord.Embed:
    """Tous les comptes Overwatch suivis sur le serveur."""
    embed = discord.Embed(
        title="\N{VIDEO GAME} Comptes Overwatch suivis",
        colour=COLOUR_NEUTRAL,
    )
    if not entries:
        embed.description = (
            "Personne pour l'instant. `/ow-inscription` pour lier un BattleTag."
        )
        return embed

    for player, ranks in entries:
        value = (
            " \N{BULLET} ".join(
                f"{ranks[role].role_label} {ranks[role].label}"
                for role in ROLES
                if role in ranks
            )
            or UNRANKED_LABEL
        )
        embed.add_field(
            name=f"{player.username or player.battletag} \N{EM DASH} <@{player.discord_id}>",
            value=value,
            inline=False,
        )
    embed.set_footer(text=FOOTER_SOURCE)
    return embed


def _platform_label(platform: str) -> str:
    return "PC" if platform == "pc" else "Console"
