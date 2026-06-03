"""Web API tests for single-job enrich."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.storage.db import Database
from agentzero.web.app import create_app
from tests.test_db import _job


def test_post_job_enrich_runs_deep_enrich_and_upserts(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    app = create_app(db_path=db_path, settings=Settings(_env_file=None, enrich_web_search=False))
    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    job_id = job.job_id
    db.close()

    def _deep(j, **kwargs):
        return j.model_copy(update={"comp_min": 180_000, "comp_max": 220_000})

    monkeypatch.setattr("agentzero.web.mutations.enrich_job_deep", _deep)

    with TestClient(app) as client:
        response = client.post(f"/api/jobs/{job_id}/enrich")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    db = Database(db_path)
    stored = db.get_job(job_id)
    assert stored is not None
    assert stored.comp_min == 180_000
    db.close()
