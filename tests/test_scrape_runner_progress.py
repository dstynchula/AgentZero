"""Tests for web scrape runner progress integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agentzero.config import Settings
from agentzero.loops.run_progress import load_scrape_progress_file, scrape_progress_path
from agentzero.storage.db import Database
from agentzero.web.scrape_runner import ScrapeRunner


@pytest.fixture
def scrape_env(tmp_path: Path):
    db_path = tmp_path / "jobs.db"
    db = Database(db_path)
    settings = Settings(_env_file=None, db_path=db_path)
    runner = ScrapeRunner()
    yield db, settings, runner, db_path
    db.close()


def test_scrape_runner_snapshot_includes_progress_fields(scrape_env):
    _db, _settings, runner, _db_path = scrape_env
    runner.state.running = True
    runner.state.phase = "enrich"
    runner.state.done = 2
    runner.state.total = 5
    runner.state.detail = "Dev @ Co"
    runner.state.last_message = "Enriching jobs (2/5)"

    snap = runner.snapshot()
    assert snap["running"] is True
    assert snap["phase"] == "enrich"
    assert snap["done"] == 2
    assert snap["total"] == 5
    assert snap["detail"] == "Dev @ Co"


def test_scrape_runner_persists_progress_file(scrape_env):
    db, settings, runner, db_path = scrape_env

    def fake_execute(*, db, settings, operator, progress):
        progress.set_phase("scrape", total=2, done=1, detail="indeed")
        return ("Done: 1 scraped, 1 new lead(s).", 1, 1, [])

    with patch("agentzero.web.scrape_runner._execute_scrape", side_effect=fake_execute):
        ok, _msg = runner.start(db=db, settings=settings, operator=None)

    assert ok is True
    import time

    deadline = time.monotonic() + 2.0
    while runner.state.running and time.monotonic() < deadline:
        time.sleep(0.05)

    path = scrape_progress_path(db_path)
    loaded = load_scrape_progress_file(path)
    assert loaded is not None
    assert loaded.running is False
    assert runner.snapshot()["phase"] in ("done", "scrape", "idle")
