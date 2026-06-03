"""Granular scrape progress fields and merge helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentzero.loops.run_progress import (
    RunProgress,
    RunProgressSnapshot,
    load_scrape_progress_file,
    merge_scrape_status,
    save_scrape_progress_file,
    scrape_progress_path,
)


def test_log_appends_and_caps(tmp_path: Path):
    path = scrape_progress_path(tmp_path / "jobs.db")
    progress = RunProgress(persist_path=path, running=True)
    progress.begin_run()
    for i in range(300):
        progress.log("info", f"line {i}")
    loaded = load_scrape_progress_file(path)
    assert loaded is not None
    assert len(loaded.logs) <= 250
    assert loaded.logs[-1]["message"] == "line 299"


def test_enter_step_persists_granular_fields(tmp_path: Path):
    path = scrape_progress_path(tmp_path / "jobs.db")
    progress = RunProgress(persist_path=path, running=True, pid=4242)
    progress.begin_run()
    progress.enter_step(
        "scrape.linkedin.query_2",
        phase="scrape",
        label="LinkedIn search (2/3)",
        total=3,
        done=1,
        detail="Principal Security Engineer",
        next_step_id="scrape.linkedin.query_3",
        next_step_label="LinkedIn: Senior Security Engineer",
        extra={"term": "Principal Security Engineer"},
    )
    loaded = load_scrape_progress_file(path)
    assert loaded is not None
    assert loaded.step_id == "scrape.linkedin.query_2"
    assert loaded.step_label == "LinkedIn search (2/3)"
    assert loaded.next_step_id == "scrape.linkedin.query_3"
    assert loaded.extra.get("term") == "Principal Security Engineer"
    assert loaded.pid == 4242
    assert loaded.step_elapsed_ms >= 0
    assert loaded.run_elapsed_ms >= 0


def test_merge_scrape_status_marks_stale_when_worker_dead():
    file_snap = RunProgressSnapshot(
        phase="scrape",
        running=True,
        step_id="scrape.linkedin.query_1",
    )
    merged = merge_scrape_status(
        file_snap=file_snap,
        runner_snap={"running": True, "errors": []},
        process_alive=False,
    )
    assert merged["stale"] is True
    assert merged["running"] is False
    assert merged["step_id"] == "scrape.linkedin.query_1"


@pytest.fixture
def scrape_env(tmp_path: Path):
    from agentzero.config import Settings
    from agentzero.storage.db import Database
    from agentzero.web.scrape_runner import ScrapeRunner

    db_path = tmp_path / "jobs.db"
    db = Database(db_path)
    settings = Settings(_env_file=None, db_path=db_path)
    runner = ScrapeRunner()
    yield db, settings, runner, db_path
    db.close()


def test_scrape_runner_stop_clears_running(scrape_env):
    db, settings, runner, db_path = scrape_env
    path = scrape_progress_path(db_path)
    save_scrape_progress_file(
        path,
        RunProgressSnapshot(
            phase="scrape",
            running=True,
            step_id="scrape.linkedin.query_1",
            message="Running",
        ),
    )
    runner.state.running = True
    ok, msg = runner.stop(db=db)
    assert ok is True
    loaded = load_scrape_progress_file(path)
    assert loaded is not None
    assert loaded.running is False
    assert loaded.cancelled is True
    snap = runner.snapshot(db=db)
    assert snap["running"] is False
    assert snap.get("cancelled") or snap.get("phase") == "cancelled"
