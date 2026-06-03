"""SQLite database backup helpers for operator data safety."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BackupResult:
    """Path to a timestamped copy of the jobs database."""

    source: Path
    backup_path: Path
    filename: str


def backup_filename(*, now: datetime | None = None) -> str:
    """Return a safe, timestamped backup file name."""
    instant = now or datetime.now(UTC)
    stamp = instant.strftime("%Y%m%d-%H%M%S")
    return f"agentzero-{stamp}.db"


def create_backup(db_path: Path, *, backups_dir: Path | None = None) -> BackupResult:
    """Copy the SQLite database to ``data/backups/agentzero-YYYYMMDD-HHMMSS.db``."""
    source = Path(db_path)
    if not source.is_file():
        raise FileNotFoundError(f"database not found: {source}")

    dest_dir = backups_dir or (source.parent / "backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = backup_filename()
    dest = dest_dir / name
    shutil.copy2(source, dest)
    return BackupResult(source=source, backup_path=dest, filename=name)
