"""Tests for thread-safe scrape run progress."""

from __future__ import annotations

import json
from pathlib import Path

from agentzero.loops.run_progress import (
    RunProgress,
    RunProgressSnapshot,
    load_scrape_progress_file,
    save_scrape_progress_file,
    scrape_progress_path,
)


def test_run_progress_snapshot_message():
    progress = RunProgress(running=True)
    progress.set_phase("enrich", total=5, done=2, detail="Engineer @ Acme")
    snap = progress.snapshot()
    assert "Enriching" in snap.message
    assert snap.done == 2
    assert snap.total == 5


def test_run_progress_updates_and_callback():
    seen: list[RunProgressSnapshot] = []

    def on_change(snap: RunProgressSnapshot) -> None:
        seen.append(snap)

    progress = RunProgress(on_change=on_change, running=True)
    progress.set_phase("scrape", total=3, done=0, detail="indeed")
    progress.step(detail="indeed")
    progress.finish()

    assert seen[-1].phase == "done"
    assert seen[-1].running is False
    assert progress.snapshot().done == 3


def test_scrape_progress_file_round_trip(tmp_path: Path):
    path = scrape_progress_path(tmp_path / "jobs.db")
    snap = RunProgressSnapshot(
        phase="rank",
        done=1,
        total=4,
        detail="PM @ Beta",
        message="Ranking jobs (1/4) — PM @ Beta",
        running=True,
    )
    save_scrape_progress_file(path, snap)
    loaded = load_scrape_progress_file(path)
    assert loaded is not None
    assert loaded.phase == "rank"
    assert loaded.running is True
    assert json.loads(path.read_text(encoding="utf-8"))["total"] == 4
