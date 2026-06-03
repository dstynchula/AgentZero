from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app


@pytest.fixture
def data_client(tmp_path: Path):
    db_path = tmp_path / "data" / "agentzero.db"
    settings = Settings(_env_file=None, db_path=db_path)
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as client:
        yield client, db_path


def test_data_page_renders(data_client):
    client, _ = data_client
    r = client.get("/data")
    assert r.status_code == 200
    assert "<h1>Data</h1>" in r.text
    assert "Make a backup of the DB" in r.text
    assert "Restore" in r.text


def test_post_backup_returns_attachment(data_client):
    client, db_path = data_client
    assert db_path.is_file()
    r = client.post("/api/data/backup")
    assert r.status_code == 200
    assert "application/octet-stream" in r.headers.get("content-type", "")
    assert r.headers.get("content-disposition", "").startswith("attachment")
    backups = list(db_path.parent.joinpath("backups").glob("agentzero-*.db"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == db_path.read_bytes()


def test_nav_includes_data(data_client):
    client, _ = data_client
    r = client.get("/data")
    assert 'href="/data"' in r.text
