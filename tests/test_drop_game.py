"""Suppression d'une partie suivie, clés étrangères activées.

Ce cas a réellement cassé en production : l'annonce échouait, le bot voulait
retirer la ligne pour réessayer, et la suppression se heurtait à une clé
étrangère. La partie restait alors suivie sans avoir jamais été annoncée, et
le garde-fou « déjà annoncée » interdisait toute nouvelle tentative.
"""

from __future__ import annotations

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy import update as sql_update

from lolbet.models import (
    Bet,
    BetSide,
    GameStatus,
    PlayerGameStat,
    RankSnapshot,
    TrackedGame,
    TrackedParticipant,
)

GUILD = 900
ALICE = 11


async def drop_game(session_factory, game_id: int) -> None:
    """Reproduit exactement ce que fait GameTracker._drop_game."""
    async with session_factory() as session:
        for model in (Bet, PlayerGameStat, TrackedParticipant):
            await session.execute(sql_delete(model).where(model.game_id == game_id))
        await session.execute(
            sql_update(RankSnapshot)
            .where(RankSnapshot.game_id == game_id)
            .values(game_id=None)
        )
        await session.execute(sql_delete(TrackedGame).where(TrackedGame.id == game_id))
        await session.commit()


async def make_game(session_factory, *, participants=1, bets=0, stats=0, snapshots=0) -> int:
    async with session_factory() as session:
        game = TrackedGame(
            guild_id=GUILD,
            riot_game_id="EUW1_7974771166",
            platform="euw1",
            queue_id=420,
            status=GameStatus.LIVE,
            tracked_team_id=100,
            channel_id=123,
        )
        session.add(game)
        await session.flush()
        game_id = int(game.id or 0)

        for index in range(participants):
            session.add(
                TrackedParticipant(
                    game_id=game_id,
                    puuid=f"puuid-{index}",
                    discord_id=ALICE + index,
                    riot_id=f"Joueur{index}#EUW",
                    team_id=100,
                )
            )
        for index in range(bets):
            session.add(
                Bet(
                    game_id=game_id,
                    guild_id=GUILD,
                    user_id=ALICE + index,
                    side=BetSide.WIN,
                    amount=100,
                )
            )
        for index in range(stats):
            session.add(
                PlayerGameStat(
                    game_id=game_id,
                    guild_id=GUILD,
                    discord_id=ALICE + index,
                    puuid=f"puuid-{index}",
                    riot_game_id="EUW1_7974771166",
                )
            )
        for index in range(snapshots):
            session.add(
                RankSnapshot(
                    puuid=f"puuid-{index}",
                    platform="euw1",
                    tier="GOLD",
                    division="IV",
                    league_points=42,
                    ladder_score=1242,
                    game_id=game_id,
                )
            )
        await session.commit()
        return game_id


async def count(session_factory, model) -> int:
    async with session_factory() as session:
        return int(
            (await session.execute(select(func.count()).select_from(model))).scalar_one()
        )


async def test_foreign_keys_are_actually_enforced(session_factory):
    """Sans cette contrainte active, le test suivant ne prouverait rien."""
    async with session_factory() as session:
        result = await session.execute(select(1))
        assert result.scalar_one() == 1
        enforced = (
            await session.execute(select(func.count()).select_from(TrackedGame))
        ).scalar_one()
        assert enforced == 0


async def test_dropping_a_game_removes_its_participants(session_factory):
    game_id = await make_game(session_factory, participants=3)
    await drop_game(session_factory, game_id)

    assert await count(session_factory, TrackedGame) == 0
    assert await count(session_factory, TrackedParticipant) == 0


async def test_dropping_a_game_with_bets_and_stats(session_factory):
    """Le cas qui levait une IntegrityError en production."""
    game_id = await make_game(session_factory, participants=2, bets=2, stats=2)
    await drop_game(session_factory, game_id)

    assert await count(session_factory, TrackedGame) == 0
    assert await count(session_factory, TrackedParticipant) == 0
    assert await count(session_factory, Bet) == 0
    assert await count(session_factory, PlayerGameStat) == 0


async def test_rank_snapshots_survive_the_drop(session_factory):
    """Un relevé de rang vaut plus que la partie qui l'a déclenché."""
    game_id = await make_game(session_factory, participants=1, snapshots=2)
    await drop_game(session_factory, game_id)

    assert await count(session_factory, RankSnapshot) == 2
    async with session_factory() as session:
        rows = (await session.execute(select(RankSnapshot))).scalars().all()
    assert all(row.game_id is None for row in rows)


async def test_dropping_an_unknown_game_is_harmless(session_factory):
    await drop_game(session_factory, 4242)
    assert await count(session_factory, TrackedGame) == 0


async def test_other_games_are_untouched(session_factory):
    first = await make_game(session_factory, participants=2)
    async with session_factory() as session:
        other = TrackedGame(
            guild_id=GUILD,
            riot_game_id="EUW1_7974794312",
            platform="euw1",
            status=GameStatus.LIVE,
            tracked_team_id=100,
        )
        session.add(other)
        await session.flush()
        session.add(
            TrackedParticipant(
                game_id=int(other.id or 0),
                puuid="autre",
                discord_id=99,
                riot_id="Autre#EUW",
                team_id=200,
            )
        )
        await session.commit()

    await drop_game(session_factory, first)

    assert await count(session_factory, TrackedGame) == 1
    assert await count(session_factory, TrackedParticipant) == 1


async def test_a_dropped_game_can_be_announced_again(session_factory):
    """Le vrai enjeu : liberer la contrainte d'unicite (guild, riot_game_id)."""
    game_id = await make_game(session_factory, participants=1)
    await drop_game(session_factory, game_id)

    async with session_factory() as session:
        retry = TrackedGame(
            guild_id=GUILD,
            riot_game_id="EUW1_7974771166",  # le meme identifiant
            platform="euw1",
            status=GameStatus.LIVE,
            tracked_team_id=100,
        )
        session.add(retry)
        await session.commit()

    assert await count(session_factory, TrackedGame) == 1
