"""Lier un compte Riot à un compte Discord.

Isolé des cogs pour être testable sans Discord : les commandes se contentent
de mettre en forme les erreurs levées ici.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Player
from ..riot.client import RiotClient, normalise_platform
from ..utils import utcnow
from .betting import BettingService

MAX_GAME_NAME = 16
MAX_TAG_LINE = 5


class RegistrationError(Exception):
    """Message destiné à être affiché tel quel au joueur."""


class InvalidRiotId(RegistrationError):
    pass


class AccountNotFound(RegistrationError):
    pass


class AlreadyLinked(RegistrationError):
    def __init__(self, message: str, other_discord_id: int) -> None:
        super().__init__(message)
        self.other_discord_id = other_discord_id


@dataclass(frozen=True, slots=True)
class LinkResult:
    created: bool
    game_name: str
    tag_line: str
    platform: str
    balance: int

    @property
    def riot_id(self) -> str:
        return f"{self.game_name}#{self.tag_line}"


def split_riot_id(raw: str) -> tuple[str, str] | None:
    """``Faker#KR1`` -> ``("Faker", "KR1")``. None si ce n'est pas un Riot ID."""
    text = (raw or "").strip()
    if "#" not in text:
        return None
    name, _, tag = text.rpartition("#")
    name, tag = name.strip(), tag.strip()
    if not name or not tag or len(name) > MAX_GAME_NAME or len(tag) > MAX_TAG_LINE:
        return None
    return name, tag


async def link_account(
    session: AsyncSession,
    riot: RiotClient,
    betting: BettingService,
    *,
    guild_id: int,
    discord_id: int,
    riot_id: str,
    region: str | None,
    default_platform: str,
) -> LinkResult:
    """Résout le Riot ID puis le lie au compte Discord donné.

    Les erreurs de l'API Riot (clé expirée, indisponibilité) remontent telles
    quelles : c'est la commande qui décide du message à afficher.
    """
    parts = split_riot_id(riot_id)
    if parts is None:
        raise InvalidRiotId(
            "Ça ne ressemble pas à un Riot ID. Utilise la forme `Pseudo#TAG`, "
            "par exemple `Faker#KR1`."
        )
    game_name, tag_line = parts
    platform = normalise_platform(region, default_platform)

    account = await riot.get_account_by_riot_id(game_name, tag_line, platform)
    if not account or not account.get("puuid"):
        raise AccountNotFound(
            f"Aucun compte **{game_name}#{tag_line}** sur `{platform}`. "
            "Vérifie l'orthographe et la région."
        )

    puuid = str(account["puuid"])
    resolved_name = str(account.get("gameName") or game_name)
    resolved_tag = str(account.get("tagLine") or tag_line)

    # Deux personnes ne peuvent pas revendiquer le même compte LoL.
    taken = (
        await session.execute(
            select(Player).where(
                Player.guild_id == guild_id,
                Player.puuid == puuid,
                Player.discord_id != discord_id,
            )
        )
    ).scalar_one_or_none()
    if taken is not None:
        raise AlreadyLinked(
            f"**{resolved_name}#{resolved_tag}** est déjà lié à "
            f"<@{taken.discord_id}> sur ce serveur.",
            taken.discord_id,
        )

    existing = (
        await session.execute(
            select(Player).where(
                Player.guild_id == guild_id, Player.discord_id == discord_id
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        session.add(
            Player(
                guild_id=guild_id,
                discord_id=discord_id,
                puuid=puuid,
                game_name=resolved_name,
                tag_line=resolved_tag,
                platform=platform,
            )
        )
        created = True
    else:
        # Un compte Discord ne suit qu'un compte LoL : on remplace.
        existing.puuid = puuid
        existing.game_name = resolved_name
        existing.tag_line = resolved_tag
        existing.platform = platform
        existing.riot_id_refreshed_at = utcnow()
        session.add(existing)
        created = False

    wallet = await betting.get_wallet(session, guild_id, discord_id)
    return LinkResult(
        created=created,
        game_name=resolved_name,
        tag_line=resolved_tag,
        platform=platform,
        balance=wallet.balance,
    )


async def unlink_account(
    session: AsyncSession, guild_id: int, discord_id: int
) -> str | None:
    """Retire le suivi. Renvoie le Riot ID retiré, ou None si rien n'était lié."""
    player = (
        await session.execute(
            select(Player).where(
                Player.guild_id == guild_id, Player.discord_id == discord_id
            )
        )
    ).scalar_one_or_none()
    if player is None:
        return None
    riot_id = player.riot_id
    await session.delete(player)
    return riot_id


async def linked_players(session: AsyncSession, guild_id: int) -> list[Player]:
    result = await session.execute(
        select(Player).where(Player.guild_id == guild_id).order_by(Player.registered_at)
    )
    return list(result.scalars().all())
