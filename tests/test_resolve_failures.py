"""Quand MATCH-V5 répond par une erreur, la résolution doit finir quelque part.

Le cas réel : une ARAM Mayhem (file 2400) que Riot refusait de servir en
MATCH-V5 (403) alors que la clé fonctionnait partout ailleurs. Le bot a
réessayé toutes les dix secondes pendant six heures — aucun message, aucun
remboursement. Un 404 abandonnait proprement après douze essais ; une erreur
API ne passait jamais par le compte à rebours.
"""

from __future__ import annotations

from types import SimpleNamespace

from lolbet.models import GameStatus, TrackedGame
from lolbet.riot.client import RiotAPIError, RiotUnauthorized, RiotUnavailable
from lolbet.services.embeds import VOID_REASONS, build_void_embed
from lolbet.services.tracker import GameTracker, _void_reason
from lolbet.utils import as_utc, utcnow

GUILD = 31


class FakeRiot:
    """Un client dont MATCH-V5 échoue toujours de la même façon."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    async def get_match(self, match_id: str, platform: str):
        self.calls += 1
        raise self.error


def make_bot(session_factory, settings, riot) -> SimpleNamespace:
    return SimpleNamespace(session_factory=session_factory, settings=settings, riot=riot)


async def pending_game(session_factory) -> int:
    async with session_factory() as session:
        game = TrackedGame(
            guild_id=GUILD,
            riot_game_id="EUW1_7987042825",
            platform="euw1",
            queue_id=2400,
            status=GameStatus.PENDING_RESULT,
            tracked_team_id=100,
            resolve_after=utcnow(),
            next_result_attempt_at=utcnow(),
        )
        session.add(game)
        await session.commit()
        return int(game.id or 0)


async def load(session_factory, game_id: int) -> TrackedGame:
    async with session_factory() as session:
        game = await session.get(TrackedGame, game_id)
        assert game is not None
        return game


# -- classification --------------------------------------------------------


def test_a_403_means_riot_refuses_this_match():
    assert _void_reason(RiotUnauthorized(403, "MATCH-V5")) == "forbidden"


def test_a_401_means_the_key_is_bad():
    assert _void_reason(RiotUnauthorized(401, "MATCH-V5")) == "bad_key"


def test_anything_else_is_a_generic_api_error():
    assert _void_reason(RiotUnavailable(503, "MATCH-V5")) == "api_error"
    assert _void_reason(RiotAPIError(429, "MATCH-V5")) == "api_error"


def test_every_reason_has_a_message_and_none_blames_the_players():
    for reason in ("forbidden", "bad_key", "api_error", "not_published"):
        text = build_void_embed("EUW1_1", None, reason=reason).description
        assert text == VOID_REASONS[reason]
        assert "rembours" in text


def test_an_unknown_reason_falls_back_to_the_generic_message():
    text = build_void_embed("EUW1_1", None, reason="???").description
    assert text == VOID_REASONS["not_published"]


# -- comportement ----------------------------------------------------------


async def test_an_api_error_now_pushes_the_next_attempt_back(session_factory, settings):
    """Avant : réessai au tick suivant, dix secondes plus tard, pour toujours."""
    riot = FakeRiot(RiotUnauthorized(403, "MATCH-V5"))
    tracker = GameTracker(make_bot(session_factory, settings, riot))
    game_id = await pending_game(session_factory)

    await tracker._resolve_pending()

    game = await load(session_factory, game_id)
    assert riot.calls == 1
    assert game.result_attempts == 1
    assert game.status == GameStatus.PENDING_RESULT
    next_at = as_utc(game.next_result_attempt_at)
    assert next_at is not None
    assert (next_at - utcnow()).total_seconds() > 20  # repoussé, pas immédiat


async def test_a_game_not_yet_due_is_left_alone(session_factory, settings):
    riot = FakeRiot(RiotUnauthorized(403, "MATCH-V5"))
    tracker = GameTracker(make_bot(session_factory, settings, riot))
    game_id = await pending_game(session_factory)

    await tracker._resolve_pending()  # premier échec : repousse
    await tracker._resolve_pending()  # pas encore l'heure : rien

    game = await load(session_factory, game_id)
    assert riot.calls == 1
    assert game.result_attempts == 1


async def test_after_the_last_attempt_the_game_is_voided_with_the_reason(
    session_factory, settings, monkeypatch
):
    riot = FakeRiot(RiotUnauthorized(403, "MATCH-V5"))
    tracker = GameTracker(make_bot(session_factory, settings, riot))
    game_id = await pending_game(session_factory)

    voided: list[tuple[int, str]] = []

    async def fake_void(gid: int, *, reason: str = "") -> None:
        voided.append((gid, reason))

    monkeypatch.setattr(tracker, "_void_game", fake_void)

    # On force chaque tentative a etre due immediatement.
    for _ in range(settings.result_max_attempts):
        async with session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            assert game is not None
            game.next_result_attempt_at = utcnow()
            session.add(game)
            await session.commit()
        await tracker._resolve_pending()

    assert riot.calls == settings.result_max_attempts
    assert voided == [(game_id, "forbidden")]


async def test_a_transient_error_keeps_the_generic_reason(
    session_factory, settings, monkeypatch
):
    riot = FakeRiot(RiotUnavailable(503, "MATCH-V5"))
    tracker = GameTracker(make_bot(session_factory, settings, riot))
    game_id = await pending_game(session_factory)

    voided: list[tuple[int, str]] = []

    async def fake_void(gid: int, *, reason: str = "") -> None:
        voided.append((gid, reason))

    monkeypatch.setattr(tracker, "_void_game", fake_void)

    for _ in range(settings.result_max_attempts):
        async with session_factory() as session:
            game = await session.get(TrackedGame, game_id)
            assert game is not None
            game.next_result_attempt_at = utcnow()
            session.add(game)
            await session.commit()
        await tracker._resolve_pending()

    assert voided == [(game_id, "api_error")]


# -- files ignorees ----------------------------------------------------------


async def _tracker_with_player(session_factory, settings, monkeypatch):
    from lolbet.models import Player

    async with session_factory() as session:
        session.add(
            Player(
                guild_id=GUILD,
                discord_id=11,
                puuid="p-mayhem",
                game_name="Joueur",
                tag_line="EUW",
                platform="euw1",
            )
        )
        await session.commit()

    tracker = GameTracker(make_bot(session_factory, settings, FakeRiot(RuntimeError())))
    announced: list[str] = []

    async def fake_announce(guild_id, players, spectator, platform, riot_game_id):
        announced.append(riot_game_id)

    monkeypatch.setattr(tracker, "_announce_for_guild", fake_announce)
    return tracker, announced


def spectator(queue: int) -> dict:
    return {"gameQueueConfigId": queue, "participants": [{"puuid": "p-mayhem"}]}


async def test_a_queue_riot_will_not_serve_is_never_announced(
    session_factory, settings, monkeypatch
):
    """ARAM Mayhem (2400) : pas de marche qu'on sait ne jamais pouvoir regler."""
    tracker, announced = await _tracker_with_player(session_factory, settings, monkeypatch)
    await tracker._on_live_game(spectator(2400), "euw1", "EUW1_1")
    assert announced == []


async def test_a_ranked_queue_is_still_announced(session_factory, settings, monkeypatch):
    tracker, announced = await _tracker_with_player(session_factory, settings, monkeypatch)
    await tracker._on_live_game(spectator(420), "euw1", "EUW1_2")
    assert announced == ["EUW1_2"]


async def test_the_allow_list_is_configurable(session_factory, settings, monkeypatch):
    """Le jour ou Riot sert le mode, une ligne de .env suffit."""
    settings.tracked_queues = {2400}
    tracker, announced = await _tracker_with_player(session_factory, settings, monkeypatch)
    await tracker._on_live_game(spectator(2400), "euw1", "EUW1_3")
    await tracker._on_live_game(spectator(420), "euw1", "EUW1_4")
    assert announced == ["EUW1_3"]


def test_the_default_list_covers_the_modes_the_bot_can_settle(settings):
    assert {420, 440, 400, 450} <= settings.tracked_queues
    assert 2400 not in settings.tracked_queues  # Mayhem : 403 en MATCH-V5
    assert 1700 not in settings.tracked_queues  # Arene : quatre equipes
