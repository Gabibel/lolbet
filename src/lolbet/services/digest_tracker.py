"""La boucle qui poste le bilan hebdomadaire.

Volontairement bête : elle se réveille toutes les dix minutes et demande
« le créneau est-il passé sans avoir été servi ? ». Pas de planificateur, pas
de dépendance en plus, et une coupure de trois jours ne fait rien manquer —
le bilan part au réveil au lieu d'être perdu.
"""

from __future__ import annotations

import asyncio

import discord
from sqlalchemy import select

from ..logging_conf import get_logger
from ..models import GuildConfig
from ..utils import utcnow
from .digest import build_digest, is_due, timezone_or_utc
from .digest_embeds import build_digest_embed

log = get_logger(__name__)

CHECK_INTERVAL_SECONDS = 600


class DigestScheduler:
    def __init__(self, bot) -> None:  # noqa: ANN001 - évite un import circulaire
        self._bot = bot
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        settings = self._bot.settings
        if not settings.digest_enabled:
            log.info("digest.disabled")
            return
        self._task = asyncio.create_task(self._loop(), name="lolbet-digest")
        log.info(
            "digest.started",
            weekday=settings.digest_weekday,
            hour=settings.digest_hour,
            timezone=settings.digest_timezone,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(30)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - filet
                log.exception("digest.tick_failed", error=str(exc))
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def tick(self) -> int:
        """Poste les bilans dus. Renvoie le nombre de bilans envoyés."""
        settings = self._bot.settings
        tz = timezone_or_utc(settings.digest_timezone)
        now = utcnow()

        async with self._bot.session_factory() as session:
            configs = list((await session.execute(select(GuildConfig))).scalars())

        sent = 0
        for config in configs:
            if not config.announce_channel_id:
                continue
            if config.last_digest_at is None:
                # Premier passage : on pose le repère au lieu de rattraper un
                # passé qu'on n'a pas vécu.
                await self._stamp(config.guild_id, now)
                log.info("digest.baseline", guild=config.guild_id)
                continue
            if not is_due(
                now,
                config.last_digest_at,
                settings.digest_weekday,
                settings.digest_hour,
                tzinfo=tz,
            ):
                continue
            if await self.post(config.guild_id, config.announce_channel_id):
                await self._stamp(config.guild_id, now)
                sent += 1
        return sent

    async def post(self, guild_id: int, channel_id: int) -> bool:
        """Compose et envoie le bilan. Faux si l'envoi a échoué."""
        channel = self._bot.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            log.warning("digest.channel_missing", guild=guild_id, channel=channel_id)
            return False

        async with self._bot.session_factory() as session:
            digest = await build_digest(
                session, guild_id, days=self._bot.settings.digest_days
            )

        try:
            await channel.send(embed=build_digest_embed(digest, days=self._bot.settings.digest_days))
        except discord.Forbidden:
            log.warning(
                "digest.cannot_post",
                guild=guild_id,
                channel=channel_id,
                hint="il manque Envoyer des messages ou Intégrer des liens",
            )
            return False
        except discord.HTTPException as exc:  # pragma: no cover - réseau
            log.warning("digest.post_failed", guild=guild_id, error=str(exc))
            return False

        log.info("digest.posted", guild=guild_id, games=digest.games)
        return True

    async def _stamp(self, guild_id: int, moment) -> None:  # noqa: ANN001
        async with self._bot.session_factory() as session:
            config = await session.get(GuildConfig, guild_id)
            if config is None:
                return
            config.last_digest_at = moment
            session.add(config)
            await session.commit()
