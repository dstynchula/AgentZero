from pathlib import Path

import pytest

from agentzero.storage.backup import create_backup


def test_create_backup_copies_db(tmp_path: Path):
    db_path = tmp_path / "data" / "agentzero.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"SQLite format 3\x00")
    result = create_backup(db_path)
    assert result.backup_path.is_file()
    assert result.backup_path.read_bytes() == db_path.read_bytes()
    assert result.filename.startswith("agentzero-")
    assert result.backup_path.parent == tmp_path / "data" / "backups"


def test_create_backup_rejects_missing_db(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="database not found"):
        create_backup(tmp_path / "missing.db")
