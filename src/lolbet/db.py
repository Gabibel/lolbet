"""Async SQLite engine with WAL enabled.

Deliberately boring: one file on local disk, no server, no managed service.
WAL matters here because the poller writes while slash commands read.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from . import models  # noqa: F401  (import registers the tables on SQLModel.metadata)
from .logging_conf import get_logger

log = get_logger(__name__)


def _sqlite_path(url: str) -> Path | None:
    """Pull the on-disk path out of a sqlite URL, or None for :memory:."""
    marker = "sqlite+aiosqlite:///"
    if not url.startswith(marker):
        return None
    raw = url[len(marker) :]
    if not raw or raw.startswith(":memory:"):
        return None
    return Path(raw)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    path = _sqlite_path(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(url, echo=echo, future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        try:
            # WAL: readers never block the writer, and the writer never blocks
            # readers. Required for a poller + slash commands on one file.
            cursor.execute("PRAGMA journal_mode=WAL")
            # NORMAL is the standard companion to WAL: durable across process
            # crashes, only at risk on a hard power loss.
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Colonnes ajoutees apres coup. create_all ne touche pas aux tables qui
# existent deja, donc une nouvelle colonne doit etre ajoutee a la main.
ADDED_COLUMNS: dict[tuple[str, str], str] = {
    ("bet", "odds"): "FLOAT NOT NULL DEFAULT 0",
}


async def ensure_columns(engine: AsyncEngine) -> list[str]:
    """Ajoute les colonnes manquantes aux tables existantes."""
    added: list[str] = []
    async with engine.begin() as conn:
        for (table, column), ddl in ADDED_COLUMNS.items():
            rows = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
            if column in {row[1] for row in rows}:
                continue
            await conn.exec_driver_sql(
                f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
            )
            added.append(f"{table}.{column}")
    if added:
        log.info("database.migrated", columns=added)
    return added


async def init_db(engine: AsyncEngine) -> None:
    """Create tables if they do not exist. No migration tool, no service."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await ensure_columns(engine)
    log.info("database.ready", url=str(engine.url).split("///")[-1])


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Commit on success, roll back on failure, always close."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def default_database_url() -> str:
    return os.environ.get("LOLBET_DATABASE_URL", "sqlite+aiosqlite:///./data/lolbet.db")
