"""Web API tests for batch enrich selected."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.storage.db import Database
from agentzero.web.app import create_app
from tests.test_db import _job


@pytest.fixture
def web_client(tmp_path):
    db_path = tmp_path / "jobs.db"
    app = create_app(db_path=db_path, settings=Settings(_env_file=None))
    with TestClient(app) as client:
        yield client, db_path, app


def test_enrich_runner_posts_selected_job_ids(web_client, monkeypatch):
    client, db_path, app = web_client
    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    runner = app.state.enrich_runner
    started: list[list[str]] = []

    def _start(*, db, settings, job_ids):
        started.append(list(job_ids))
        return True, "started"

    monkeypatch.setattr(runner, "start", _start)
    response = client.post(
        "/api/jobs/enrich-selected",
        json={"job_ids": [job.job_id]},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["ok"] is True
    assert started == [[job.job_id]]
