#!/usr/bin/env python3
"""Build the AgentZero Docker image with elapsed time and ETA progress.

Usage (from repo root):

    python scripts/docker_build.py
    python scripts/docker_build.py --ci          # docker build (no compose)
    python scripts/docker_build.py --no-cache

Writes heartbeat status to ``data/.docker-build-status.json`` (timings only, no secrets).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentzero.loops.progress import BuildProgress, BuildStep  # noqa: E402

_STEP_MARKER = re.compile(r"agentzero-build-step:\s*(\w+)", re.IGNORECASE)
_MANIFEST_PATH = REPO_ROOT / "docker" / "build.manifest.json"
_STATUS_PATH = REPO_ROOT / "data" / ".docker-build-status.json"
_BENCHMARKS_PATH = REPO_ROOT / "data" / "docker-build-benchmarks.json"


def _load_manifest(path: Path) -> list[BuildStep]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        BuildStep(
            id=str(item["id"]),
            label=str(item["label"]),
            estimated_seconds=float(item["estimated_seconds"]),
        )
        for item in data
    ]


def _load_benchmarks() -> dict[str, float]:
    if not _BENCHMARKS_PATH.is_file():
        return {}
    try:
        raw = json.loads(_BENCHMARKS_PATH.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in raw.items()}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _apply_benchmarks(steps: list[BuildStep], benchmarks: dict[str, float]) -> list[BuildStep]:
    out: list[BuildStep] = []
    for step in steps:
        est = benchmarks.get(step.id, step.estimated_seconds)
        out.append(BuildStep(id=step.id, label=step.label, estimated_seconds=est))
    return out


def _write_status(progress: BuildProgress, *, stalled: bool | None = None) -> None:
    _STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = progress.status_dict(stalled=stalled)
    tmp = _STATUS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(_STATUS_PATH)


def _save_benchmarks(progress: BuildProgress, steps: list[BuildStep]) -> None:
    benchmarks = {s.id: progress._estimates[i] for i, s in enumerate(steps)}  # noqa: SLF001
    _BENCHMARKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _BENCHMARKS_PATH.write_text(json.dumps(benchmarks, indent=2) + "\n", encoding="utf-8")


def _heartbeat_loop(progress: BuildProgress, stop: threading.Event) -> None:
    while not stop.wait(progress.heartbeat_seconds):
        progress.print_status()
        _write_status(progress)


def _parse_line(progress: BuildProgress, line: str) -> None:
    progress.touch_output()
    match = _STEP_MARKER.search(line)
    if match:
        progress.advance_to_step_id(match.group(1).lower())


def run_build(*, use_compose: bool, no_cache: bool) -> int:
    if not _MANIFEST_PATH.is_file():
        print(f"ERROR: manifest not found: {_MANIFEST_PATH}", file=sys.stderr)
        return 1

    steps = _apply_benchmarks(_load_manifest(_MANIFEST_PATH), _load_benchmarks())
    stall_sec = float(os.environ.get("AGENTZERO_BUILD_STALL_SEC", "180"))
    progress = BuildProgress(steps, stall_seconds=stall_sec)
    progress.print_status(suffix="starting")
    _write_status(progress)

    cmd: list[str]
    if use_compose:
        cmd = ["docker", "compose", "build", "--progress=plain"]
    else:
        cmd = ["docker", "build", "--progress=plain", "-t", "agentzero:ci", "."]
    if no_cache:
        cmd.append("--no-cache")

    stop = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat_loop, args=(progress, stop), daemon=True)
    heartbeat.start()

    proc = subprocess.Popen(  # noqa: S603
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            stripped = line.rstrip()
            if stripped:
                _parse_line(progress, stripped)
            if progress.is_stalled():
                progress.print_status(suffix="(no docker output)")
                _write_status(progress, stalled=True)
    finally:
        stop.set()
        heartbeat.join(timeout=2.0)

    code = proc.wait()
    progress.finish_all()
    if code == 0:
        _save_benchmarks(progress, steps)
    total = progress.elapsed_sec
    print(
        f"\nBuild {'succeeded' if code == 0 else 'failed'} in {_format_total(total)} (exit {code})",
        flush=True,
    )
    _write_status(progress, stalled=False)
    return code


def _format_total(seconds: float) -> str:
    from agentzero.loops.progress import _format_duration

    return _format_duration(seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentZero Docker image with ETA progress")
    parser.add_argument("--ci", action="store_true", help="Use docker build instead of compose")
    parser.add_argument("--no-cache", action="store_true", help="Pass --no-cache to docker")
    args = parser.parse_args()
    try:
        return run_build(use_compose=not args.ci, no_cache=args.no_cache)
    except FileNotFoundError:
        print("ERROR: docker not found on PATH", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        print("\nBuild cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
