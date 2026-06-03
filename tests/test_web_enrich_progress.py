"""Tests for enrich batch RunProgress wiring."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.enrich.batch import run_enrich_batch
from agentzero.loops.run_progress import RunProgress, load_scrape_progress_file
from agentzero.models import JobPosting
from agentzero.storage.db import Database
from agentzero.web.app import create_app


@pytest.fixture
def web_client(tmp_path):
    db_path = tmp_path / "jobs.db"
    app = create_app(db_path=db_path, settings=Settings(_env_file=None))
    with TestClient(app) as client:
        yield client, db_path, app


def _job(**kwargs) -> JobPosting:
    base = dict(
        title="Engineer",
        company="Acme",
        url="https://www.linkedin.com/jobs/view/1",
        source="linkedin",
        description="Enough text " * 30,
    )
    base.update(kwargs)
    return JobPosting(**base)


def test_run_enrich_batch_updates_run_progress_done_total(tmp_path, monkeypatch):
    db = Database(tmp_path / "t.db")
    job_a = _job(url="https://www.linkedin.com/jobs/view/1")
    job_b = _job(url="https://www.linkedin.com/jobs/view/2", title="Staff Engineer")
    db.upsert_job(job_a)
    db.upsert_job(job_b)
    progress_path = tmp_path / "enrich_progress.json"
    progress = RunProgress(persist_path=progress_path, running=True)
    progress.begin_run()
    progress.enter_step("enrich.parallel", phase="enrich", label="Enrich", total=2, done=0)

    settings = Settings(
        _env_file=None,
        enrich_web_search=False,
        enrich_max_concurrency=2,
    )
    monkeypatch.setattr(
        "agentzero.enrich.batch.enrich_job_deep",
        lambda job, **kwargs: job,
    )

    result = run_enrich_batch(
        db,
        [job_a.job_id, job_b.job_id],
        settings=settings,
        max_workers=2,
        fetch_detail=False,
        glassdoor_lookup=False,
        web_search=False,
        allow_browser=False,
        browser_delay_seconds=0,
        run_progress=progress,
    )
    assert result.total == 2
    loaded = load_scrape_progress_file(progress_path)
    assert loaded is not None
    assert loaded.done == 2
    assert loaded.total == 2
    assert any("Acme" in entry.get("message", "") for entry in loaded.logs)


def test_jobs_page_includes_enrich_progress_panel(web_client):
    client, _, _ = web_client
    response = client.get("/jobs")
    assert response.status_code == 200
    html = response.text
    assert "enrich-log-viewer" in html
    assert "enrich-progress-bar" in html
    assert "agentzeroPollEnrich" in html


def test_api_enrich_stop_marks_cancelled(web_client):
    client, db_path, app = web_client
    from agentzero.loops.run_progress import (
        RunProgressSnapshot,
        enrich_progress_path,
        save_scrape_progress_file,
    )

    save_scrape_progress_file(
        enrich_progress_path(db_path),
        RunProgressSnapshot(
            phase="enrich",
            running=True,
            done=1,
            total=3,
            step_id="enrich.parallel",
        ),
    )
    response = client.post("/api/enrich/stop")
    assert response.status_code == 200
    body = response.json()
    assert body.get("ok") is True
    assert body.get("phase") == "cancelled"
    assert body.get("running") is False


def test_api_enrich_returns_logs_and_granular_fields(web_client, monkeypatch):
    client, db_path, app = web_client
    from agentzero.loops.run_progress import (
        RunProgressSnapshot,
        enrich_progress_path,
        save_scrape_progress_file,
        scrape_log_entry,
    )

    monkeypatch.setattr(app.state.enrich_runner, "_thread_alive", lambda: True)
    save_scrape_progress_file(
        enrich_progress_path(db_path),
        RunProgressSnapshot(
            phase="enrich",
            running=True,
            done=2,
            total=5,
            step_id="enrich.parallel",
            step_label="HTTP detail",
            run_elapsed_ms=5000,
            logs=(scrape_log_entry("info", "job done", step_id="enrich.job"),),
        ),
    )
    response = client.get("/api/enrich")
    body = response.json()
    assert body.get("logs")
    assert body.get("step_id") == "enrich.parallel"
    assert body.get("run_elapsed_ms") == 5000
