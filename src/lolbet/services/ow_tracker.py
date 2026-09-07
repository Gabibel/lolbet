"""Boucle de suivi des rangs Overwatch.

Une seule boucle, très lente : le rang n'est réévalué par le jeu que toutes
les 5 victoires ou 15 défaites, et le profil public se rafraîchit avec du
retard. Relire toutes les quinze minutes suffit largement, et reste poli avec
une API tierce gratuite qu'on ne paie pas.

Ce que cette boucle **ne fait pas**, faute de données : détecter une partie en
cours, ou lire une partie terminée. Overwatch n'expose ni l'une ni l'autre.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

import discord

from ..logging_conf import get_logger
from ..models import GuildConfig, OverwatchPlayer
from ..overwatch.client import (
    OverFastError,
    OwPlayerNotFound,
    OwUnavailable,
)
from ..overwatch.rank import OwRank, parse_summary, season_of
from ..utils import utcnow
from .ow_embeds import build_ow_change_embed
from .ow_taunts import ow_taunt_content
from .overwatch import apply_ranks, linked_ow_players

log = get_logger(__name__)

# Espacement entre deux comptes, pour ne pas partir en rafale sur une API
# gratuite. Le nombre de joueurs suivis se compte sur les doigts d'une main.
SPACING_SECONDS = 2.0


class OverwatchTracker:
    def __init__(self, bot) -> None:  # noqa: ANN001 - évite un import circulaire
        self._bot = bot
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        if not self._bot.settings.overwatch_enabled:
            log.info("ow.disabled")
            return
        self._task = asyncio.create_task(self._loop(), name="lolbet-overwatch")
        log.info("ow.started", interval=self._bot.settings.overwatch_poll_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    # -- boucle -----------------------------------------------------------

    async def _loop(self) -> None:
        interval = self._bot.settings.overwatch_poll_seconds
        # Laisser le bot finir de démarrer avant le premier passage.
        await asyncio.sleep(10)
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - filet
                log.exception("ow.poll_failed", error=str(exc))
            await asyncio.sleep(interval)

    async def poll_once(self) -> int:
        """Relit chaque compte suivi. Renvoie le nombre de comptes lus."""
        async with self._bot.session_factory() as session:
            players = await linked_ow_players(session)

        if not players:
            log.debug("ow.poll_pass", accounts=0)
            return 0

        # Un même BattleTag peut être inscrit sur plusieurs serveurs : on ne
        # le lit qu'une fois, et on annonce dans chaque serveur concerné.
        grouped: dict[tuple[str, str], list[OverwatchPlayer]] = defaultdict(list)
        for player in players:
            grouped[(player.battletag, player.platform)].append(player)

        for index, ((battletag, platform), owners) in enumerate(grouped.items()):
            if index:
                await asyncio.sleep(SPACING_SECONDS)
            await self._refresh_account(battletag, platform, owners)

        log.info("ow.poll_pass", accounts=len(grouped))
        return len(grouped)

    async def _refresh_account(
        self, battletag: str, platform: str, owners: list[OverwatchPlayer]
    ) -> None:
        try:
            summary = await self._bot.overfast.refresh_summary(battletag)
        except OwPlayerNotFound:
            await self._note_error(
                owners, "profil introuvable (BattleTag changé, ou profil supprimé)"
            )
            log.warning("ow.player_not_found", battletag=battletag)
            return
        except (OwUnavailable, OverFastError) as exc:
            # Panne d'un service tiers : on ne touche pas aux relevés.
            await self._note_error(owners, "OverFast indisponible")
            log.warning("ow.fetch_failed", battletag=battletag, error=str(exc))
            return

        ranks = parse_summary(summary, platform)
        season = season_of(summary, platform)

        async with self._bot.session_factory() as session:
            changes = await apply_ranks(
                session,
                battletag=battletag,
                platform=platform,
                ranks=ranks,
                season=season,
            )
            for owner in owners:
                stored = await session.get(OverwatchPlayer, owner.id)
                if stored is None:
                    continue
                stored.username = summary.get("username") or stored.username
                stored.avatar_url = summary.get("avatar") or stored.avatar_url
                stored.last_checked_at = utcnow()
                stored.last_error = "" if ranks else "aucun rang compétitif visible"
                session.add(stored)
            await session.commit()

        if not changes:
            return

        log.info(
            "ow.rank_changed",
            battletag=battletag,
            roles=[change.role for change in changes],
        )
        for owner in owners:
            await self._announce(owner, changes, ranks, season)

    async def _note_error(self, owners: list[OverwatchPlayer], reason: str) -> None:
        async with self._bot.session_factory() as session:
            for owner in owners:
                stored = await session.get(OverwatchPlayer, owner.id)
                if stored is None:
                    continue
                stored.last_checked_at = utcnow()
                stored.last_error = reason
                session.add(stored)
            await session.commit()

    async def _announce(
        self,
        player: OverwatchPlayer,
        changes: list,
        ranks: dict[str, OwRank],
        season: int | None,
    ) -> None:
        bot = self._bot
        async with bot.session_factory() as session:
            config = await session.get(GuildConfig, player.guild_id)
            channel_id = config.announce_channel_id if config else None

        if not channel_id:
            log.warning(
                "ow.no_channel",
                guild=player.guild_id,
                hint="lance /salon pour choisir ou annoncer",
            )
            return

        channel = bot.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            log.warning("ow.channel_missing", guild=player.guild_id, channel=channel_id)
            return

        embed = build_ow_change_embed(player, changes, ranks=ranks, season=season)
        content = ow_taunt_content(changes, seed=f"{player.battletag}:{season}")
        try:
            await channel.send(content=f"<@{player.discord_id}> {content}", embed=embed)
        except discord.Forbidden:
            log.warning(
                "ow.cannot_post",
                guild=player.guild_id,
                channel=channel_id,
                hint="il manque Envoyer des messages ou Intégrer des liens",
            )
        except discord.HTTPException as exc:  # pragma: no cover - réseau
            log.warning("ow.post_failed", guild=player.guild_id, error=str(exc))
