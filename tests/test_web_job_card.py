from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app
from agentzero.web.jobs import job_detail_for_ui
from tests.test_db import _job


def test_job_detail_for_ui_includes_description(tmp_path):
    from agentzero.storage.db import Database

    db = Database(tmp_path / "t.db")
    job = _job(description="Build APIs and lead the platform team.")
    db.upsert_job(job)
    detail = job_detail_for_ui(db, job.job_id)
    db.close()
    assert detail is not None
    assert detail["description"] == "Build APIs and lead the platform team."


def test_job_detail_for_ui_empty_description(tmp_path):
    from agentzero.storage.db import Database

    db = Database(tmp_path / "t.db")
    job = _job()
    db.upsert_job(job)
    detail = job_detail_for_ui(db, job.job_id)
    db.close()
    assert detail is not None
    assert detail["description"] == ""


@pytest.fixture
def card_client(tmp_path: Path):
    db_path = tmp_path / "t.db"
    settings = Settings(_env_file=None, db_path=db_path)
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as client:
        yield client, db_path


def test_job_detail_page_renders_description(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job(description="Build APIs and lead the platform team.")
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert "<h2>Description</h2>" in r.text
    assert "Build APIs and lead the platform team." in r.text


def test_job_detail_page_shows_empty_description_placeholder(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert "No description stored yet" in r.text
