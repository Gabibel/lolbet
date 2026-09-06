"""Live-game detection, bet locking and result resolution.

Two plain asyncio loops, no scheduler dependency:

* the poll loop walks every registered PUUID across POLL_INTERVAL_SECONDS,
  spacing requests evenly instead of firing them in a burst;
* the maintenance loop locks expired betting windows and resolves finished
  games.

Rate-limit shape: players already inside a tracked game are not polled at all.
One "watcher" PUUID per live game is polled to notice the game ending, so a
five-stack costs one spectator call per interval instead of five.
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import discord
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy import update as sql_update

from ..logging_conf import get_logger
from ..models import (
    Bet,
    GameStatus,
    GuildConfig,
    Player,
    PlayerGameStat,
    RankSnapshot,
    TrackedGame,
    TrackedParticipant,
)
from .backup import backup_async, database_path
from .history import player_form, record_game_stats
from .progression import capture_after_game
from ..riot.client import RiotAPIError, RiotUnauthorized, build_match_id
from ..utils import as_utc, from_epoch_ms, utcnow
from .betting import Pool
from .embeds import (
    TEAM_NAMES,
    build_game_embed,
    build_lock_embed,
    build_result_embed,
    build_bad_key_embed,
    build_void_embed,
    queue_name,
    side_labels_for,
)
from .enrichment import base_card, find_team_id
from .scoring import score_match
from .taunts import build_taunt_content

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import LoLBet

log = get_logger(__name__)

# A game that never disappears from spectator (player unregistered, Riot bug)
# would otherwise hold bets hostage forever.
MAX_GAME_AGE = timedelta(hours=3)
BACKUP_CHECK_EVERY = timedelta(minutes=30)
CACHE_PURGE_EVERY = timedelta(hours=1)
RESOLVE_BACKOFF_BASE = 30  # seconds, doubled per attempt, capped below
RESOLVE_BACKOFF_MAX = 300


@dataclass(frozen=True, slots=True)
class PollTarget:
    puuid: str
    platform: str
    game_ids: tuple[int, ...] = ()

    @property
    def is_watcher(self) -> bool:
        return bool(self.game_ids)


class GameTracker:
    def __init__(self, bot: LoLBet) -> None:
        self._bot = bot
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()
        self._last_cache_purge = utcnow()
        self._last_backup = utcnow() - timedelta(days=1)
        self._last_key_alert: datetime | None = None
        # De quoi répondre à « est-ce que le bot surveille vraiment ? »
        self.last_poll_at: datetime | None = None
        self.last_pass_targets = 0
        self.polls_done = 0
        self.games_seen = 0

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        if self._tasks:
            return
        self._stopping.clear()
        self._tasks = [
            asyncio.create_task(self._poll_loop(), name="lolbet-poll"),
            asyncio.create_task(self._maintenance_loop(), name="lolbet-maintenance"),
        ]
        log.info("tracker.started", interval=self._bot.settings.poll_interval_seconds)

    async def stop(self) -> None:
        self._stopping.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _sleep(self, seconds: float) -> None:
        """Sleep, but wake immediately on shutdown."""
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)
        except TimeoutError:
            pass

    # -- poll loop --------------------------------------------------------

    async def _poll_loop(self) -> None:
        await self._bot.wait_until_ready()
        while not self._stopping.is_set():
            try:
                targets = await self._build_targets()
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("tracker.targets_failed", error=str(exc))
                await self._sleep(10)
                continue

            interval = self._bot.settings.poll_interval_seconds
            self.last_pass_targets = len(targets)
            watchers = sum(1 for t in targets if t.is_watcher)
            log.info(
                "tracker.poll_pass",
                targets=len(targets),
                watching=watchers,
                interval=interval,
            )
            if not targets:
                log.warning("tracker.nobody_to_poll")
                await self._sleep(interval)
                continue

            # Spread the pass across the whole interval so the per-second
            # window never sees a spike.
            gap = max(0.0, interval / len(targets))
            for target in targets:
                if self._stopping.is_set():
                    break
                try:
                    await self._poll_target(target)
                    self.polls_done += 1
                    self.last_poll_at = utcnow()
                except RiotUnauthorized as exc:
                    log.error("tracker.bad_api_key", error=str(exc))
                    await self._alert_bad_key()
                    await self._sleep(60)
                    break
                except RiotAPIError as exc:
                    log.warning("tracker.poll_failed", puuid=target.puuid[:8], error=str(exc))
                except Exception as exc:  # pragma: no cover - defensive
                    log.exception("tracker.poll_error", error=str(exc))
                await self._sleep(gap)

    async def _build_targets(self) -> list[PollTarget]:
        async with self._bot.session_factory() as session:
            live_games = (
                (
                    await session.execute(
                        select(TrackedGame).where(
                            TrackedGame.status.in_([GameStatus.LIVE, GameStatus.LOCKED])
                        )
                    )
                )
                .scalars()
                .all()
            )
            live_ids = [g.id for g in live_games if g.id is not None]
            busy: set[str] = set()
            if live_ids:
                busy = set(
                    (
                        await session.execute(
                            select(TrackedParticipant.puuid).where(
                                TrackedParticipant.game_id.in_(live_ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            players = (await session.execute(select(Player))).scalars().all()

        watchers: dict[tuple[str, str], list[int]] = {}
        for game in live_games:
            if not game.watcher_puuid or game.id is None:
                continue
            watchers.setdefault((game.watcher_puuid, game.platform), []).append(game.id)

        targets = [
            PollTarget(puuid, platform, tuple(game_ids))
            for (puuid, platform), game_ids in watchers.items()
        ]
        seen = set(watchers)

        idle: list[PollTarget] = []
        for player in players:
            key = (player.puuid, player.platform)
            if key in seen or player.puuid in busy:
                continue
            seen.add(key)
            idle.append(PollTarget(player.puuid, player.platform))

        # Watchers first (ending a game is time-sensitive), then everybody
        # else in a rotating order so nobody is permanently last in line.
        random.shuffle(idle)
        return targets + idle

    async def _poll_target(self, target: PollTarget) -> None:
        spectator = await self._bot.riot.get_active_game(target.puuid, target.platform)
        current_id = (
            build_match_id(target.platform, spectator.get("gameId", ""))
            if spectator
            else None
        )

        if target.is_watcher:
            await self._reconcile_watched(target.game_ids, current_id)

        if spectator and current_id:
            self.games_seen += 1
            log.info(
                "tracker.in_game",
                puuid=target.puuid[:8],
                game=current_id,
                queue=spectator.get("gameQueueConfigId"),
            )
            await self._on_live_game(spectator, target.platform, current_id)

    async def _reconcile_watched(self, game_ids: tuple[int, ...], current_id: str | None) -> None:
        """Any watched game that is no longer the live one has finished."""
        now = utcnow()
        async with self._bot.session_factory() as session:
            for game_id in game_ids:
                game = await session.get(TrackedGame, game_id)
                if game is None or game.status not in (GameStatus.LIVE, GameStatus.LOCKED):
                    continue
                if game.riot_game_id == current_id:
                    continue
                game.status = GameStatus.PENDING_RESULT
                # MATCH-V5 takes a moment to publish; do not ask immediately.
                game.resolve_after = now + timedelta(
                    seconds=self._bot.settings.result_delay_seconds
                )
                game.next_result_attempt_at = game.resolve_after
                session.add(game)
                log.info("tracker.game_ended", game=game.riot_game_id, guild=game.guild_id)
            await session.commit()

    # -- announcing -------------------------------------------------------

    async def _on_live_game(
        self, spectator: dict[str, Any], platform: str, riot_game_id: str
    ) -> None:
        """Announce this game in every guild that has not seen it yet."""
        puuids = {
            str(p.get("puuid") or "") for p in (spectator.get("participants") or [])
        } - {""}
        if not puuids:
            return

        async with self._bot.session_factory() as session:
            registered = (
                (await session.execute(select(Player).where(Player.puuid.in_(puuids))))
                .scalars()
                .all()
            )
        if not registered:
            return

        by_guild: dict[int, list[Player]] = {}
        for player in registered:
            by_guild.setdefault(player.guild_id, []).append(player)

        for guild_id, guild_players in by_guild.items():
            try:
                await self._announce_for_guild(
                    guild_id, guild_players, spectator, platform, riot_game_id
                )
            except Exception as exc:  # pragma: no cover - defensive
                log.exception(
                    "tracker.announce_failed", guild=guild_id, game=riot_game_id, error=str(exc)
                )

    async def _announce_for_guild(
        self,
        guild_id: int,
        players: list[Player],
        spectator: dict[str, Any],
        platform: str,
        riot_game_id: str,
    ) -> None:
        bot = self._bot
        now = utcnow()

        async with bot.session_factory() as session:
            existing = (
                await session.execute(
                    select(TrackedGame).where(
                        TrackedGame.guild_id == guild_id,
                        TrackedGame.riot_game_id == riot_game_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return  # already announced, even across a restart

            config = await session.get(GuildConfig, guild_id)
            channel_id = config.announce_channel_id if config else None

        if not channel_id:
            log.warning(
                "tracker.no_channel",
                guild=guild_id,
                hint="lance /salon pour choisir ou annoncer",
            )
            return

        channel = bot.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            log.warning("tracker.channel_missing", guild=guild_id, channel=channel_id)
            return

        tracked = {p.puuid: p.discord_id for p in players}
        team_id = find_team_id(spectator, set(tracked))
        started_at = from_epoch_ms(spectator.get("gameStartTime")) or now
        lock_at = started_at + timedelta(seconds=bot.settings.bet_lock_seconds)
        # Detected late (long game already running): announce it already locked
        # rather than pretending there is a betting window.
        status = GameStatus.LIVE if lock_at > now else GameStatus.LOCKED

        async with bot.session_factory() as session:
            game = TrackedGame(
                guild_id=guild_id,
                riot_game_id=riot_game_id,
                platform=platform,
                queue_id=int(spectator.get("gameQueueConfigId") or 0),
                status=status,
                tracked_team_id=team_id,
                game_start_at=started_at,
                detected_at=now,
                lock_at=lock_at,
                channel_id=channel_id,
                watcher_puuid=players[0].puuid,
                spectator_json=json.dumps(spectator, separators=(",", ":")),
            )
            session.add(game)
            await session.flush()
            game_id = int(game.id or 0)

            for participant in spectator.get("participants") or []:
                puuid = str(participant.get("puuid") or "")
                if puuid not in tracked:
                    continue
                player = next(p for p in players if p.puuid == puuid)
                session.add(
                    TrackedParticipant(
                        game_id=game_id,
                        puuid=puuid,
                        discord_id=player.discord_id,
                        riot_id=player.riot_id,
                        champion_id=int(participant.get("championId") or 0),
                        team_id=int(participant.get("teamId") or 100),
                    )
                )
            await session.commit()
            stored_status = game.status

        # Phase 1: spectator data only, so this goes out immediately and
        # betting opens here.
        await bot.ddragon.ensure_fresh()
        card = base_card(
            spectator,
            platform=platform,
            riot_game_id=riot_game_id,
            tracked=tracked,
            lock_at=lock_at,
        )
        card.tracked_team_id = team_id
        embed = build_game_embed(card, Pool(), bot.ddragon, status=stored_status)

        from ..views import BetView

        view = (
            BetView(game_id, card.labels) if stored_status == GameStatus.LIVE else None
        )

        # La ligne existe deja en base : les boutons ont besoin de son id. Tout
        # ce qui suit doit donc etre annule en cas d'echec, sinon la partie
        # reste suivie sans avoir jamais ete annoncee - et le garde-fou
        # « deja annoncee » empeche toute nouvelle tentative.
        message: discord.Message | None = None
        try:
            message = await channel.send(embed=embed, view=view)

            thread_id = (
                await self._open_thread(message, card, riot_game_id)
                if bot.settings.use_threads
                else None
            )

            async with bot.session_factory() as session:
                stored = await session.get(TrackedGame, game_id)
                if stored is not None:
                    stored.message_id = message.id
                    stored.thread_id = thread_id
                    session.add(stored)
                    await session.commit()
        except discord.Forbidden:
            log.warning("tracker.cannot_post", guild=guild_id, channel=channel_id)
            await self._abandon_announcement(game_id, message)
            return
        except discord.HTTPException as exc:
            log.warning("tracker.post_failed", guild=guild_id, error=str(exc))
            await self._abandon_announcement(game_id, message)
            return
        except Exception as exc:
            # Tout le reste : embed refuse, bug de rendu, coupure reseau. La
            # partie sera redetectee au prochain sondage.
            log.exception(
                "tracker.announce_crashed",
                game=riot_game_id,
                guild=guild_id,
                error=str(exc),
            )
            await self._abandon_announcement(game_id, message)
            return

        log.info(
            "tracker.announced",
            game=riot_game_id,
            guild=guild_id,
            players=len(tracked),
            status=stored_status,
        )

        # Phase 2: rank + mastery + level, then edit the same message.
        asyncio.create_task(self._enrich_later(game_id))

    async def _open_thread(
        self, message: discord.Message, card, riot_game_id: str
    ) -> int | None:
        names = ", ".join(p.riot_id.split("#")[0] for p in card.tracked)[:60] or riot_game_id
        try:
            thread = await message.create_thread(
                name=f"{names} - {queue_name(card.queue_id)}"[:100],
                auto_archive_duration=1440,
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.info("tracker.no_thread", game=riot_game_id, error=str(exc))
            return None
        return thread.id

    async def _enrich_later(self, game_id: int) -> None:
        try:
            await asyncio.sleep(self._bot.settings.enrich_delay_seconds)
            await self._bot.updater.refresh(game_id, allow_fetch=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("tracker.enrich_failed", game_id=game_id, error=str(exc))

    async def _abandon_announcement(
        self, game_id: int, message: discord.Message | None
    ) -> None:
        """Efface toute trace d'une annonce ratee, pour pouvoir reessayer."""
        if message is not None:
            # Un message poste sans ligne en base aurait des boutons morts.
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                log.warning("tracker.orphan_message", message_id=message.id)
        await self._drop_game(game_id)

    async def _drop_game(self, game_id: int) -> None:
        """Supprime une partie et tout ce qui la reference.

        L'ordre est explicite : SQLite applique les cles etrangeres et aucune
        relation ORM n'est declaree entre ces tables, donc SQLAlchemy ne sait
        pas dans quel ordre supprimer. Sans ca, la suppression echoue et laisse
        une partie fantome qui ne pourra plus jamais etre annoncee.
        """
        async with self._bot.session_factory() as session:
            for model in (Bet, PlayerGameStat, TrackedParticipant):
                await session.execute(
                    sql_delete(model).where(model.game_id == game_id)
                )
            # Un releve de rang survit a la partie : on le detache au lieu de
            # perdre un point de progression.
            await session.execute(
                sql_update(RankSnapshot)
                .where(RankSnapshot.game_id == game_id)
                .values(game_id=None)
            )
            await session.execute(
                sql_delete(TrackedGame).where(TrackedGame.id == game_id)
            )
            await session.commit()
        log.info("tracker.game_dropped", game_id=game_id)

    # -- maintenance loop -------------------------------------------------

    async def _maintenance_loop(self) -> None:
        await self._bot.wait_until_ready()
        while not self._stopping.is_set():
            try:
                await self._lock_expired()
                await self._resolve_pending()
                await self._expire_stale()
                await self._housekeeping()
                await self._maybe_backup()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("tracker.maintenance_failed", error=str(exc))
            await self._sleep(self._bot.settings.maintenance_interval_seconds)

    async def _lock_expired(self) -> None:
        now = utcnow()
        to_refresh: list[int] = []
        async with self._bot.session_factory() as session:
            games = (
                (
                    await session.execute(
                        select(TrackedGame).where(TrackedGame.status == GameStatus.LIVE)
                    )
                )
                .scalars()
                .all()
            )
            for game in games:
                lock_at = as_utc(game.lock_at)
                if lock_at is None or lock_at > now:
                    continue
                game.status = GameStatus.LOCKED
                session.add(game)
                if game.id is not None:
                    to_refresh.append(game.id)
            await session.commit()

        for game_id in to_refresh:
            log.info("tracker.locked", game_id=game_id)
            await self._bot.updater.refresh(game_id)
            if self._bot.settings.announce_lock:
                await self._post_lock_notice(game_id)

    async def _post_lock_notice(self, game_id: int) -> None:
        """Say in the channel that the window closed, with the final pool."""
        bot = self._bot
        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            if game is None:
                return
            participants = (
                (
                    await session.execute(
                        select(TrackedParticipant).where(TrackedParticipant.game_id == game_id)
                    )
                )
                .scalars()
                .all()
            )
            pool = await bot.betting.pool(session, game_id)
            bets = await bot.betting.bets_for_game(session, game_id)

        embed = build_lock_embed(
            riot_game_id=game.riot_game_id,
            tracked_names=[p.riot_id for p in participants] or [game.riot_game_id],
            pool=pool,
            bets=bets,
            tracked_team_name=TEAM_NAMES.get(game.tracked_team_id, "L'équipe suivie"),
            window_seconds=bot.settings.bet_lock_seconds,
            labels=side_labels_for(participants, game.tracked_team_id),
        )
        await self._post_followup(game_id, embed)

    async def _expire_stale(self) -> None:
        """Force very old live games into resolution so bets are never stuck."""
        now = utcnow()
        async with self._bot.session_factory() as session:
            games = (
                (
                    await session.execute(
                        select(TrackedGame).where(
                            TrackedGame.status.in_([GameStatus.LIVE, GameStatus.LOCKED])
                        )
                    )
                )
                .scalars()
                .all()
            )
            changed = False
            for game in games:
                detected = as_utc(game.detected_at) or now
                if now - detected < MAX_GAME_AGE:
                    continue
                game.status = GameStatus.PENDING_RESULT
                game.resolve_after = now
                game.next_result_attempt_at = now
                session.add(game)
                changed = True
                log.warning("tracker.stale_game", game=game.riot_game_id)
            if changed:
                await session.commit()

    async def _resolve_pending(self) -> None:
        now = utcnow()
        async with self._bot.session_factory() as session:
            pending = (
                (
                    await session.execute(
                        select(TrackedGame).where(
                            TrackedGame.status == GameStatus.PENDING_RESULT
                        )
                    )
                )
                .scalars()
                .all()
            )
        for game in pending:
            due = as_utc(game.next_result_attempt_at) or as_utc(game.resolve_after) or now
            if due > now:
                continue
            try:
                await self._resolve_game(int(game.id or 0))
            except RiotAPIError as exc:
                log.warning("tracker.resolve_api_error", game=game.riot_game_id, error=str(exc))
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("tracker.resolve_failed", game=game.riot_game_id, error=str(exc))

    async def _resolve_game(self, game_id: int) -> None:
        bot = self._bot
        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            if game is None or game.status != GameStatus.PENDING_RESULT:
                return
            riot_game_id, platform = game.riot_game_id, game.platform

        match = await bot.riot.get_match(riot_game_id, platform)
        if match is None:
            await self._schedule_retry(game_id)
            return

        scores = score_match(match)
        winning_team = scores.winning_team_id

        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            if game is None or game.status != GameStatus.PENDING_RESULT:
                return
            participants = (
                (
                    await session.execute(
                        select(TrackedParticipant).where(TrackedParticipant.game_id == game_id)
                    )
                )
                .scalars()
                .all()
            )
            # La forme est lue AVANT d'enregistrer la partie : c'est ce
            # qui permet de dire « troisième défaite d'affilée » plutôt
            # que de compter la partie en cours deux fois.
            forms = {
                p.puuid: await player_form(session, game.guild_id, p.discord_id)
                for p in participants
            }
            tracked_won = winning_team == game.tracked_team_id
            settlement = await bot.betting.settle(session, game, tracked_won)
            await record_game_stats(session, game, scores, participants)
            game.status = GameStatus.RESOLVED
            game.winning_team_id = winning_team
            game.resolved_at = utcnow()
            session.add(game)
            await session.commit()
            snapshot = (
                game.riot_game_id,
                game.queue_id,
                game.tracked_team_id,
                game.id,
            )

        # Les rangs sont relus AVANT de composer le récap : c'est ce qui
        # permet d'y afficher les LP gagnés ou perdus.
        rank_changes = await self._capture_ranks(game_id, participants)

        tracked_puuids = {p.puuid for p in participants}
        # Les vannes ne visent que des joueurs inscrits volontairement,
        # et uniquement sur leurs statistiques de la partie.
        taunts = build_taunt_content(
            scores,
            {p.puuid: p.discord_id for p in participants},
            seed=snapshot[0],
            forms=forms,
            rank_changes=rank_changes,
        )
        embed = build_result_embed(
            riot_game_id=snapshot[0],
            queue_id=snapshot[1],
            scores=scores,
            tracked_puuids=tracked_puuids,
            tracked_team_id=snapshot[2],
            settlement=settlement,
            ddragon=bot.ddragon,
            rank_changes=rank_changes,
        )
        await self._post_followup(game_id, embed, content=taunts)
        await bot.updater.refresh(game_id)
        log.info(
            "tracker.resolved",
            game=snapshot[0],
            won=winning_team == snapshot[2],
            payouts=settlement.total_paid,
        )

    async def _schedule_retry(self, game_id: int) -> None:
        bot = self._bot
        now = utcnow()
        give_up = False
        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            if game is None:
                return
            game.result_attempts += 1
            if game.result_attempts >= bot.settings.result_max_attempts:
                give_up = True
            else:
                delay = min(
                    RESOLVE_BACKOFF_MAX, RESOLVE_BACKOFF_BASE * (2 ** (game.result_attempts - 1))
                )
                game.next_result_attempt_at = now + timedelta(seconds=delay)
                log.info(
                    "tracker.match_not_ready",
                    game=game.riot_game_id,
                    attempt=game.result_attempts,
                    retry_in=delay,
                )
            session.add(game)
            await session.commit()

        if give_up:
            await self._void_game(game_id)

    async def _void_game(self, game_id: int) -> None:
        bot = self._bot
        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            if game is None or game.status == GameStatus.VOID:
                return
            settlement = await bot.betting.refund_all(session, game)
            game.status = GameStatus.VOID
            game.resolved_at = utcnow()
            session.add(game)
            await session.commit()
            riot_game_id = game.riot_game_id

        log.warning("tracker.voided", game=riot_game_id, refunded=settlement.pool.total)
        await self._post_followup(game_id, build_void_embed(riot_game_id, settlement))
        await bot.updater.refresh(game_id)

    async def _post_followup(
        self, game_id: int, embed: discord.Embed, content: str | None = None
    ) -> None:
        """Post in the game thread when there is one, else in the channel.

        Without a thread the message replies to the announcement, so the two
        stay visually linked however far the channel has scrolled.
        """
        async with self._bot.session_factory() as session:
            game = await session.get(TrackedGame, game_id)
        if game is None:
            return
        destination = await self._bot.updater.destination(game)
        if destination is None:
            log.warning("tracker.no_destination", game=game.riot_game_id)
            return
        reference = None if game.thread_id else self._bot.updater.reference(game)
        try:
            await destination.send(content=content, embed=embed, reference=reference)
        except discord.HTTPException as exc:
            # A deleted announcement makes the reference invalid; resend plain.
            log.warning("tracker.followup_retry", game=game.riot_game_id, error=str(exc))
            try:
                await destination.send(content=content, embed=embed)
            except (discord.Forbidden, discord.HTTPException) as inner:
                log.warning(
                    "tracker.followup_failed", game=game.riot_game_id, error=str(inner)
                )
        except discord.Forbidden as exc:
            log.warning("tracker.followup_failed", game=game.riot_game_id, error=str(exc))

    async def _capture_ranks(self, game_id: int, participants: list) -> dict:
        """Relève le rang des joueurs suivis juste après la partie.

        Renvoie les écarts par puuid. Un échec de relevé ne bloque jamais le
        récapitulatif : on l'affiche simplement sans les LP.
        """
        bot = self._bot
        changes: dict = {}
        async with bot.session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            if game is None:
                return changes
            for participant in participants:
                try:
                    change = await capture_after_game(
                        session,
                        bot.riot,
                        puuid=participant.puuid,
                        platform=game.platform,
                        game_id=game_id,
                    )
                except Exception as exc:  # jamais bloquant
                    log.warning("tracker.rank_capture_failed", error=str(exc))
                    continue
                if change is not None:
                    changes[participant.puuid] = change
            await session.commit()
        return changes

    async def _alert_bad_key(self) -> None:
        """Prévient dans Discord que la clé Riot est refusée."""
        bot = self._bot
        if not bot.settings.alert_bad_key:
            return
        now = utcnow()
        cooldown = timedelta(hours=bot.settings.alert_cooldown_hours)
        if self._last_key_alert and now - self._last_key_alert < cooldown:
            return
        self._last_key_alert = now

        async with bot.session_factory() as session:
            configs = (
                (await session.execute(select(GuildConfig)))
                .scalars()
                .all()
            )

        embed = build_bad_key_embed()
        for config in configs:
            if not config.announce_channel_id:
                continue
            channel = bot.get_channel(config.announce_channel_id)
            if not isinstance(channel, discord.abc.Messageable):
                continue
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException) as exc:
                log.warning("tracker.alert_failed", error=str(exc))

    async def _maybe_backup(self) -> None:
        """Sauvegarde la base une fois par jour."""
        bot = self._bot
        if not bot.settings.backup_enabled:
            return
        now = utcnow()
        if now - self._last_backup < timedelta(
            hours=bot.settings.backup_interval_hours
        ):
            return
        self._last_backup = now
        path = database_path(bot.settings.database_url)
        if path is None:
            return
        await backup_async(path, keep=bot.settings.backup_keep)

    async def _housekeeping(self) -> None:
        now = utcnow()
        if now - self._last_cache_purge < CACHE_PURGE_EVERY:
            return
        self._last_cache_purge = now
        await self._bot.ddragon.ensure_fresh()
        removed = await self._bot.cache.purge_expired()
        log.info("tracker.cache_purged", removed=removed, size=self._bot.cache.size)
