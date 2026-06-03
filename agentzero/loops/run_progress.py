"""Thread-safe run progress for web UI and cross-process scrape status."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agentzero.loops.progress import Progress


@dataclass(frozen=True, slots=True)
class RunProgressSnapshot:
    phase: str = "idle"
    done: int = 0
    total: int = 0
    detail: str = ""
    message: str = ""
    running: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "done": self.done,
            "total": self.total,
            "detail": self.detail,
            "message": self.message,
            "running": self.running,
        }


def scrape_progress_path(db_path: Path) -> Path:
    return db_path.parent / "scrape_progress.json"


def load_scrape_progress_file(path: Path) -> RunProgressSnapshot | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return RunProgressSnapshot(
        phase=str(data.get("phase") or "idle"),
        done=int(data.get("done") or 0),
        total=int(data.get("total") or 0),
        detail=str(data.get("detail") or ""),
        message=str(data.get("message") or ""),
        running=bool(data.get("running")),
    )


def save_scrape_progress_file(path: Path, snapshot: RunProgressSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), indent=2) + "\n", encoding="utf-8")


def _format_message(phase: str, done: int, total: int, detail: str) -> str:
    labels = {
        "starting": "Starting scrape",
        "scrape": "Scraping job boards",
        "validate": "Validating listings",
        "filter": "Filtering listings",
        "enrich": "Enriching jobs",
        "rank": "Ranking jobs",
        "done": "Scrape complete",
        "error": "Scrape failed",
    }
    label = labels.get(phase, phase.capitalize())
    if total > 0:
        line = f"{label} ({done}/{total})"
    else:
        line = label
    if detail:
        line = f"{line} — {detail}"
    return line


class RunProgress:
    """Track scrape phase progress; optionally persist to disk for MCP polling."""

    def __init__(
        self,
        *,
        persist_path: Path | None = None,
        running: bool = False,
        on_change: Callable[[RunProgressSnapshot], None] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._persist_path = persist_path
        self._on_change = on_change
        self._phase = "idle"
        self._done = 0
        self._total = 0
        self._detail = ""
        self._running = running

    def set_running(self, running: bool) -> None:
        with self._lock:
            self._running = running
            if not running and self._phase not in ("done", "error"):
                self._phase = "done"
        self._persist()

    def set_phase(
        self,
        phase: str,
        *,
        total: int = 0,
        done: int = 0,
        detail: str = "",
    ) -> None:
        with self._lock:
            self._phase = phase
            self._total = max(0, total)
            self._done = max(0, min(done, self._total) if self._total else done)
            self._detail = detail
        self._persist()

    def step(self, *, detail: str = "") -> None:
        with self._lock:
            if self._total > 0:
                self._done = min(self._done + 1, self._total)
            else:
                self._done += 1
            if detail:
                self._detail = detail
        self._persist()

    def finish(self, *, phase: str = "done", detail: str = "") -> None:
        with self._lock:
            self._phase = phase
            if self._total > 0:
                self._done = self._total
            self._detail = detail
            self._running = False
        self._persist()

    def error(self, message: str) -> None:
        with self._lock:
            self._phase = "error"
            self._detail = message
            self._running = False
        self._persist()

    def snapshot(self) -> RunProgressSnapshot:
        with self._lock:
            message = _format_message(self._phase, self._done, self._total, self._detail)
            return RunProgressSnapshot(
                phase=self._phase,
                done=self._done,
                total=self._total,
                detail=self._detail,
                message=message,
                running=self._running,
            )

    def _persist(self) -> None:
        snap = self.snapshot()
        if self._persist_path is not None:
            save_scrape_progress_file(self._persist_path, snap)
        if self._on_change is not None:
            self._on_change(snap)


class RunProgressAdapter(Progress):
    """Bridge CLI ``Progress`` to ``RunProgress`` for enrich/rank steps."""

    def __init__(
        self,
        total: int,
        *,
        label: str,
        run_progress: RunProgress,
        phase: str,
    ) -> None:
        super().__init__(total, label=label)
        self._run_progress = run_progress
        self._phase = phase
        self._run_progress.set_phase(phase, total=total, done=0)

    def step(self, detail: str = "") -> None:
        super().step(detail)
        self._run_progress.step(detail=detail)

    def finish(self, summary: str = "") -> None:
        super().finish(summary)
        snap = self._run_progress.snapshot()
        self._run_progress.set_phase(
            self._phase,
            total=snap.total,
            done=snap.total,
            detail=summary or snap.detail,
        )
