"""BuildProgress ETA and stall helpers."""

from __future__ import annotations

import json
from pathlib import Path

from agentzero.loops.progress import BuildProgress, BuildStep


def _steps() -> list[BuildStep]:
    return [
        BuildStep(id="base", label="Base", estimated_seconds=10),
        BuildStep(id="pip", label="Pip", estimated_seconds=20),
    ]


def test_advance_to_step_id_updates_index():
    progress = BuildProgress(_steps(), stall_seconds=999)
    assert progress.advance_to_step_id("base") is False
    assert progress.step_index == 1
    assert progress.advance_to_step_id("pip") is True
    assert progress.step_index == 2


def test_format_line_contains_eta():
    progress = BuildProgress(_steps())
    line = progress.format_line()
    assert "[build 1/2]" in line
    assert "elapsed" in line
    assert "ETA total" in line


def test_status_dict_roundtrip():
    progress = BuildProgress(_steps())
    data = progress.status_dict()
    assert data["phase"] == "base"
    assert data["step_total"] == 2
    assert "elapsed_sec" in data


def test_load_manifest(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps([{"id": "x", "label": "X", "estimated_seconds": 5}]),
        encoding="utf-8",
    )
    from agentzero.loops.progress import BuildStep as BS

    data = json.loads(manifest.read_text(encoding="utf-8"))
    steps = [BS(id=i["id"], label=i["label"], estimated_seconds=i["estimated_seconds"]) for i in data]
    assert steps[0].id == "x"


def test_is_stalled_when_no_output(monkeypatch):
    base = 1000.0
    clock = {"t": base}

    def fake_monotonic() -> float:
        return clock["t"]

    monkeypatch.setattr("agentzero.loops.progress.time.monotonic", fake_monotonic)
    progress = BuildProgress(_steps(), stall_seconds=180)
    progress.touch_output()
    clock["t"] = base + 200.0
    assert progress.is_stalled() is True
