"""Sauvegardes quotidiennes de la base SQLite.

Faites depuis le bot plutôt que par une tâche cron : pas de configuration
serveur à ne pas oublier, et ça marche à l'identique sur une VM, un Pi ou un
PC Windows.

L'API ``backup`` de SQLite est utilisée plutôt qu'une copie de fichier : elle
produit un instantané cohérent même pendant que le bot écrit, ce qu'un ``cp``
ne garantit pas en mode WAL.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import date
from pathlib import Path

from ..logging_conf import get_logger

log = get_logger(__name__)

BACKUP_DIR_NAME = "backups"
PREFIX = "lolbet-"
SUFFIX = ".db"


def database_path(database_url: str) -> Path | None:
    """Chemin du fichier SQLite, ou None si la base n'est pas sur disque."""
    marker = "sqlite+aiosqlite:///"
    if not database_url.startswith(marker):
        return None
    raw = database_url[len(marker) :]
    if not raw or raw.startswith(":memory:"):
        return None
    return Path(raw)


def _backup_name(day: date) -> str:
    return f"{PREFIX}{day.isoformat()}{SUFFIX}"


def prune(directory: Path, keep: int) -> list[Path]:
    """Supprime les sauvegardes les plus anciennes. Renvoie celles retirées."""
    if keep < 1:
        return []
    existing = sorted(
        (p for p in directory.glob(f"{PREFIX}*{SUFFIX}") if p.is_file()),
        key=lambda p: p.name,
        reverse=True,
    )
    removed: list[Path] = []
    for path in existing[keep:]:
        try:
            path.unlink()
            removed.append(path)
        except OSError as exc:  # pragma: no cover - filesystem
            log.warning("backup.prune_failed", path=str(path), error=str(exc))
    return removed


def backup_now(source: Path, *, keep: int = 7, day: date | None = None) -> Path | None:
    """Écrit un instantané du jour et purge les anciens. Bloquant."""
    if not source.exists():
        log.warning("backup.no_database", path=str(source))
        return None

    directory = source.parent / BACKUP_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / _backup_name(day or date.today())

    connection = sqlite3.connect(source)
    try:
        destination = sqlite3.connect(target)
        try:
            connection.backup(destination)
        finally:
            destination.close()
    finally:
        connection.close()

    prune(directory, keep)
    log.info("backup.written", path=str(target), size=target.stat().st_size)
    return target


async def backup_async(source: Path, *, keep: int = 7) -> Path | None:
    """Version non bloquante : la copie part dans un thread."""
    try:
        return await asyncio.to_thread(backup_now, source, keep=keep)
    except Exception as exc:  # une sauvegarde ratée ne doit pas tuer le bot
        log.error("backup.failed", error=str(exc))
        return None


def latest_backup(source: Path) -> Path | None:
    directory = source.parent / BACKUP_DIR_NAME
    if not directory.is_dir():
        return None
    backups = sorted(directory.glob(f"{PREFIX}*{SUFFIX}"), key=lambda p: p.name)
    return backups[-1] if backups else None
