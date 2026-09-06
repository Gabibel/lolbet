"""Saisons, palmarès, progression de rang et sauvegardes."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from lolbet.models import RankSnapshot
from lolbet.riot.rank import RankInfo
from lolbet.services.backup import backup_now, database_path, latest_backup, prune
from lolbet.services.progression import (
    latest_snapshot,
    progression,
    record_snapshot,
    snapshot_label,
    sparkline,
)
from lolbet.services.seasons import (
    SeasonError,
    close_season,
    current_season,
    ensure_season,
    hall_of_fame,
    past_seasons,
    standings_of,
)
from lolbet.utils import utcnow

GUILD = 555
ALICE, BOB, CAROL = 11, 22, 33


async def give(session_factory, betting, user_id: int, balance: int, *, won=0, lost=0):
    async with session_factory() as session:
        wallet = await betting.get_wallet(session, GUILD, user_id)
        wallet.balance = balance
        wallet.bets_won = won
        wallet.bets_lost = lost
        wallet.net_profit = balance - 1000
        session.add(wallet)
        await session.commit()


# -- saisons ---------------------------------------------------------------


async def test_a_season_is_created_on_demand(session_factory):
    async with session_factory() as session:
        season = await ensure_season(session, GUILD, starting_balance=1000)
        await session.commit()
    assert season.number == 1
    assert season.ended_at is None
    assert season.name == "Saison 1"


async def test_ensure_is_idempotent(session_factory):
    async with session_factory() as session:
        first = await ensure_season(session, GUILD, starting_balance=1000)
        await session.commit()
    async with session_factory() as session:
        second = await ensure_season(session, GUILD, starting_balance=1000)
        await session.commit()
    assert first.id == second.id


async def test_closing_freezes_the_standings(session_factory, betting):
    await give(session_factory, betting, ALICE, 2500, won=5, lost=1)
    await give(session_factory, betting, BOB, 1800, won=3, lost=2)
    await give(session_factory, betting, CAROL, 400, won=0, lost=4)

    async with session_factory() as session:
        await ensure_season(session, GUILD, starting_balance=1000)
        closed = await close_season(session, GUILD, starting_balance=1000)
        await session.commit()

    assert [s.user_id for s in closed.standings] == [ALICE, BOB, CAROL]
    assert [s.position for s in closed.standings] == [1, 2, 3]
    assert closed.champion.user_id == ALICE
    assert closed.champion.balance == 2500


async def test_closing_resets_every_wallet(session_factory, betting):
    await give(session_factory, betting, ALICE, 2500, won=5, lost=1)
    async with session_factory() as session:
        await ensure_season(session, GUILD, starting_balance=1000)
        await close_season(session, GUILD, starting_balance=1000)
        await session.commit()

    async with session_factory() as session:
        wallet = await betting.get_wallet(session, GUILD, ALICE)
    assert wallet.balance == 1000
    assert wallet.bets_won == 0
    assert wallet.net_profit == 0


async def test_a_new_season_opens_immediately(session_factory, betting):
    """Les paris ne doivent jamais etre bloques par une cloture."""
    await give(session_factory, betting, ALICE, 1200)
    async with session_factory() as session:
        await ensure_season(session, GUILD, starting_balance=1000)
        await close_season(session, GUILD, starting_balance=1000)
        await session.commit()

    async with session_factory() as session:
        season = await current_season(session, GUILD)
    assert season is not None
    assert season.number == 2
    assert season.ended_at is None


async def test_closing_without_a_season_is_refused(session_factory):
    async with session_factory() as session:
        with pytest.raises(SeasonError):
            await close_season(session, GUILD, starting_balance=1000)


async def test_closing_without_players_is_refused(session_factory):
    async with session_factory() as session:
        await ensure_season(session, GUILD, starting_balance=1000)
        with pytest.raises(SeasonError):
            await close_season(session, GUILD, starting_balance=1000)


async def test_the_archive_survives_the_reset(session_factory, betting):
    await give(session_factory, betting, ALICE, 3000)
    async with session_factory() as session:
        await ensure_season(session, GUILD, starting_balance=1000)
        closed = await close_season(session, GUILD, starting_balance=1000)
        await session.commit()
        season_id = int(closed.season.id or 0)

    async with session_factory() as session:
        standings = await standings_of(session, season_id)
    assert standings[0].balance == 3000  # le solde d'avant remise a zero


async def test_hall_of_fame_counts_titles(session_factory, betting):
    for _ in range(2):
        await give(session_factory, betting, ALICE, 5000)
        await give(session_factory, betting, BOB, 1000)
        async with session_factory() as session:
            await ensure_season(session, GUILD, starting_balance=1000)
            await close_season(session, GUILD, starting_balance=1000)
            await session.commit()

    async with session_factory() as session:
        titles = await hall_of_fame(session, GUILD)
        seasons = await past_seasons(session, GUILD)
    assert titles[0] == (ALICE, 2)
    assert len(seasons) == 2


async def test_seasons_are_scoped_to_their_guild(session_factory, betting):
    await give(session_factory, betting, ALICE, 1500)
    async with session_factory() as session:
        await ensure_season(session, GUILD, starting_balance=1000)
        await ensure_season(session, 999, starting_balance=1000)
        await session.commit()
    async with session_factory() as session:
        assert (await current_season(session, GUILD)).number == 1
        assert (await current_season(session, 999)).number == 1
        assert await past_seasons(session, 999) == []


# -- progression -----------------------------------------------------------


def rank(tier="GOLD", division="IV", lp=0):
    return RankInfo("RANKED_SOLO_5x5", tier, division, lp, wins=10, losses=10)


async def test_a_snapshot_is_written_once(session_factory):
    async with session_factory() as session:
        first = await record_snapshot(
            session, puuid="p1", platform="euw1", rank=rank(lp=20)
        )
        await session.commit()
    assert first is not None

    async with session_factory() as session:
        again = await record_snapshot(
            session, puuid="p1", platform="euw1", rank=rank(lp=20)
        )
        await session.commit()
    assert again is None  # rien n'a bouge, rien n'est ecrit


async def test_a_changed_rank_is_written(session_factory):
    async with session_factory() as session:
        await record_snapshot(session, puuid="p1", platform="euw1", rank=rank(lp=20))
        await session.commit()
    async with session_factory() as session:
        second = await record_snapshot(
            session, puuid="p1", platform="euw1", rank=rank(lp=42)
        )
        await session.commit()
    assert second is not None
    assert second.league_points == 42


async def test_progression_measures_the_ladder_delta(session_factory):
    async with session_factory() as session:
        for lp in (0, 40, 75):
            snapshot = await record_snapshot(
                session, puuid="p1", platform="euw1", rank=rank(lp=lp)
            )
            snapshot.captured_at = utcnow() - timedelta(days=10 - lp // 20)
            session.add(snapshot)
        await session.commit()

    async with session_factory() as session:
        data = await progression(session, "p1", days=30)
    assert data.has_data
    assert data.delta == 75
    assert len(data.snapshots) == 3


async def test_progression_without_data_is_empty(session_factory):
    async with session_factory() as session:
        data = await progression(session, "inconnu", days=30)
    assert data.has_data is False
    assert data.delta == 0


async def test_latest_snapshot_is_the_most_recent(session_factory):
    async with session_factory() as session:
        await record_snapshot(session, puuid="p1", platform="euw1", rank=rank(lp=10))
        await record_snapshot(session, puuid="p1", platform="euw1", rank=rank(lp=60))
        await session.commit()
    async with session_factory() as session:
        newest = await latest_snapshot(session, "p1")
    assert newest.league_points == 60


def test_snapshot_label_reads_in_french():
    snapshot = RankSnapshot(
        puuid="p1", platform="euw1", tier="DIAMOND", division="IV", league_points=32
    )
    assert "Diamant" in snapshot_label(snapshot)


def test_sparkline_needs_two_points():
    assert sparkline([]) == ""
    one = [RankSnapshot(puuid="p", platform="euw1", tier="GOLD", ladder_score=100)]
    assert sparkline(one) == ""


def test_sparkline_draws_the_shape():
    points = [
        RankSnapshot(puuid="p", platform="euw1", tier="GOLD", ladder_score=score)
        for score in (100, 150, 200)
    ]
    drawing = sparkline(points)
    assert len(drawing) == 3
    assert drawing[0] != drawing[-1]  # ca monte


# -- sauvegardes -----------------------------------------------------------


def test_database_path_is_extracted():
    assert database_path("sqlite+aiosqlite:///./data/lolbet.db") == __import__(
        "pathlib"
    ).Path("./data/lolbet.db")
    assert database_path("sqlite+aiosqlite:///:memory:") is None
    assert database_path("postgresql://host/db") is None


def test_backup_writes_a_readable_copy(tmp_path):
    source = tmp_path / "lolbet.db"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE wallet (user_id INTEGER, balance INTEGER)")
    connection.execute("INSERT INTO wallet VALUES (11, 4242)")
    connection.commit()
    connection.close()

    target = backup_now(source, keep=7)

    assert target is not None and target.exists()
    restored = sqlite3.connect(target)
    assert restored.execute("SELECT balance FROM wallet").fetchone()[0] == 4242
    restored.close()


def test_backup_of_a_missing_database_is_harmless(tmp_path):
    assert backup_now(tmp_path / "absente.db") is None


def test_old_backups_are_pruned(tmp_path):
    directory = tmp_path / "backups"
    directory.mkdir()
    for day in range(1, 11):
        (directory / f"lolbet-2026-01-{day:02d}.db").write_text("x", encoding="utf-8")

    removed = prune(directory, keep=3)

    remaining = sorted(p.name for p in directory.glob("lolbet-*.db"))
    assert len(remaining) == 3
    assert len(removed) == 7
    # Les plus recentes sont gardees.
    assert remaining[-1] == "lolbet-2026-01-10.db"


def test_backup_replaces_the_same_day(tmp_path):
    source = tmp_path / "lolbet.db"
    sqlite3.connect(source).close()
    first = backup_now(source, day=date(2026, 1, 1))
    second = backup_now(source, day=date(2026, 1, 1))
    assert first == second
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def test_latest_backup_is_found(tmp_path):
    source = tmp_path / "lolbet.db"
    sqlite3.connect(source).close()
    assert latest_backup(source) is None
    backup_now(source, day=date(2026, 1, 1))
    newest = backup_now(source, day=date(2026, 2, 1))
    assert latest_backup(source) == newest


async def test_progression_never_mixes_two_queues(session_factory):
    """Un rang flex et un rang solo ne se comparent pas."""
    from lolbet.riot.rank import FLEX_QUEUE, SOLO_QUEUE

    async with session_factory() as session:
        flex = RankInfo(FLEX_QUEUE, "SILVER", "II", 40)
        await record_snapshot(session, puuid="p9", platform="euw1", rank=flex)
        solo = RankInfo(SOLO_QUEUE, "DIAMOND", "IV", 10)
        await record_snapshot(session, puuid="p9", platform="euw1", rank=solo)
        await session.commit()

    async with session_factory() as session:
        data = await progression(session, "p9", days=30)

    # Le releve le plus recent est en solo : seuls les releves solo comptent.
    assert all(s.queue == SOLO_QUEUE for s in data.snapshots)
    assert data.delta == 0  # un seul releve solo, donc aucun ecart


async def test_progression_can_be_asked_for_a_specific_queue(session_factory):
    from lolbet.riot.rank import FLEX_QUEUE

    async with session_factory() as session:
        for lp in (10, 60):
            await record_snapshot(
                session,
                puuid="p9",
                platform="euw1",
                rank=RankInfo(FLEX_QUEUE, "SILVER", "II", lp),
            )
        await session.commit()

    async with session_factory() as session:
        data = await progression(session, "p9", days=30, queue=FLEX_QUEUE)

    assert data.delta == 50
