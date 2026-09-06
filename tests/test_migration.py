"""Ajout de colonnes à une base déjà en service.

``create_all`` ne touche pas aux tables existantes : une colonne ajoutée après
coup au modèle n'apparaîtrait jamais, et toute lecture planterait sur une base
de production. C'est exactement le cas de ``bet.odds``.
"""

from __future__ import annotations

import sqlite3

import pytest

from lolbet.db import ADDED_COLUMNS, create_engine, ensure_columns, init_db


def columns_of(path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def make_old_database(path) -> None:
    """Une table ``bet`` telle qu'elle existait avant les cotes fixes."""
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE bet (
            id INTEGER NOT NULL PRIMARY KEY,
            game_id INTEGER NOT NULL,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            side VARCHAR(8) NOT NULL,
            amount INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            payout INTEGER,
            settled_at DATETIME
        )
        """
    )
    connection.execute(
        "INSERT INTO bet (id, game_id, guild_id, user_id, side, amount, created_at) "
        "VALUES (1, 1, 10, 11, 'WIN', 250, '2026-09-06 08:00:00')"
    )
    connection.commit()
    connection.close()


async def test_a_missing_column_is_added(tmp_path):
    path = tmp_path / "old.db"
    make_old_database(path)
    assert "odds" not in columns_of(path, "bet")

    engine = create_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    try:
        added = await ensure_columns(engine)
    finally:
        await engine.dispose()

    assert added == ["bet.odds"]
    assert "odds" in columns_of(path, "bet")


async def test_existing_rows_keep_their_data(tmp_path):
    """Une migration qui perdrait les paris en cours serait pire que le bug."""
    path = tmp_path / "old.db"
    make_old_database(path)

    engine = create_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    try:
        await ensure_columns(engine)
    finally:
        await engine.dispose()

    connection = sqlite3.connect(path)
    row = connection.execute("SELECT amount, side, odds FROM bet WHERE id = 1").fetchone()
    connection.close()
    assert row == (250, "WIN", 0.0)  # la cote par défaut vaut zéro, pas NULL


async def test_running_it_twice_changes_nothing(tmp_path):
    path = tmp_path / "old.db"
    make_old_database(path)

    engine = create_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    try:
        first = await ensure_columns(engine)
        second = await ensure_columns(engine)
    finally:
        await engine.dispose()

    assert first == ["bet.odds"]
    assert second == []


async def test_a_fresh_database_needs_no_migration(tmp_path):
    path = tmp_path / "neuf.db"
    engine = create_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    try:
        await init_db(engine)
        added = await ensure_columns(engine)
    finally:
        await engine.dispose()

    assert added == []
    assert "odds" in columns_of(path, "bet")


@pytest.mark.parametrize(("table", "column"), list(ADDED_COLUMNS))
async def test_every_declared_column_exists_on_a_fresh_database(tmp_path, table, column):
    """Le modèle et la liste de migrations ne doivent pas diverger."""
    path = tmp_path / "neuf.db"
    engine = create_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    try:
        await init_db(engine)
    finally:
        await engine.dispose()

    assert column in columns_of(path, table)
