"""Thread-safe run progress for web UI and cross-process scrape status."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from agentzero.loops.progress import Progress

ScrapeLogLevel = Literal["info", "warn", "error", "debug"]
SCRAPE_LOG_MAX = 250
SCRAPE_LOG_LOGGER_NAMES = (
    "agentzero.scrape",
    "agentzero.loops",
    "agentzero.enrich",
    "agentzero.web.scrape_runner",
)

# High-level scrape pipeline steps (used for plan + next_step hints).
DEFAULT_SCRAPE_PLAN: tuple[tuple[str, str], ...] = (
    ("starting", "Prepare settings and profile"),
    ("scrape", "Scrape job boards"),
    ("validate", "Validate listings"),
    ("filter", "Filter and enrich listings"),
    ("enrich", "Enrich backfill queue"),
    ("rank", "Rank vs résumé"),
    ("done", "Complete"),
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def scrape_log_entry(
    level: ScrapeLogLevel,
    message: str,
    *,
    step_id: str = "",
) -> dict[str, str]:
    return {
        "ts": _utc_now_iso(),
        "level": level,
        "message": message,
        "step_id": step_id,
    }


def _elapsed_ms(started_mono: float | None) -> int:
    if started_mono is None:
        return 0
    return max(0, int((time.monotonic() - started_mono) * 1000))


def _parse_plan(data: object) -> list[dict[str, str]]:
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "step_id": str(item.get("step_id") or ""),
                "label": str(item.get("label") or ""),
                "status": str(item.get("status") or "pending"),
            }
        )
    return out


def _parse_extra(data: object) -> dict[str, Any]:
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}
    return {}


def _parse_logs(data: object) -> tuple[dict[str, str], ...]:
    if not isinstance(data, list):
        return ()
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "ts": str(item.get("ts") or ""),
                "level": str(item.get("level") or "info"),
                "message": str(item.get("message") or ""),
                "step_id": str(item.get("step_id") or ""),
            }
        )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class RunProgressSnapshot:
    phase: str = "idle"
    done: int = 0
    total: int = 0
    detail: str = ""
    message: str = ""
    running: bool = False
    step_id: str = ""
    step_label: str = ""
    step_index: int = 0
    step_total: int = 0
    step_elapsed_ms: int = 0
    run_elapsed_ms: int = 0
    run_started_at: str = ""
    step_started_at: str = ""
    next_step_id: str = ""
    next_step_label: str = ""
    plan: tuple[dict[str, str], ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)
    pid: int | None = None
    stale: bool = False
    cancelled: bool = False
    logs: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "done": self.done,
            "total": self.total,
            "detail": self.detail,
            "message": self.message,
            "running": self.running,
            "step_id": self.step_id,
            "step_label": self.step_label,
            "step_index": self.step_index,
            "step_total": self.step_total,
            "step_elapsed_ms": self.step_elapsed_ms,
            "run_elapsed_ms": self.run_elapsed_ms,
            "run_started_at": self.run_started_at,
            "step_started_at": self.step_started_at,
            "next_step_id": self.next_step_id,
            "next_step_label": self.next_step_label,
            "plan": [dict(entry) for entry in self.plan],
            "extra": dict(self.extra),
            "pid": self.pid,
            "stale": self.stale,
            "cancelled": self.cancelled,
            "logs": [dict(entry) for entry in self.logs],
        }


def scrape_progress_path(db_path: Path) -> Path:
    return db_path.parent / "scrape_progress.json"


def enrich_progress_path(db_path: Path) -> Path:
    return db_path.parent / "enrich_progress.json"


def load_scrape_progress_file(path: Path) -> RunProgressSnapshot | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    plan = tuple(_parse_plan(data.get("plan")))
    return RunProgressSnapshot(
        phase=str(data.get("phase") or "idle"),
        done=int(data.get("done") or 0),
        total=int(data.get("total") or 0),
        detail=str(data.get("detail") or ""),
        message=str(data.get("message") or ""),
        running=bool(data.get("running")),
        step_id=str(data.get("step_id") or ""),
        step_label=str(data.get("step_label") or ""),
        step_index=int(data.get("step_index") or 0),
        step_total=int(data.get("step_total") or 0),
        step_elapsed_ms=int(data.get("step_elapsed_ms") or 0),
        run_elapsed_ms=int(data.get("run_elapsed_ms") or 0),
        run_started_at=str(data.get("run_started_at") or ""),
        step_started_at=str(data.get("step_started_at") or ""),
        next_step_id=str(data.get("next_step_id") or ""),
        next_step_label=str(data.get("next_step_label") or ""),
        plan=plan,
        extra=_parse_extra(data.get("extra")),
        pid=int(data["pid"]) if data.get("pid") is not None else None,
        stale=bool(data.get("stale")),
        cancelled=bool(data.get("cancelled")),
        logs=_parse_logs(data.get("logs")),
    )


def save_scrape_progress_file(path: Path, snapshot: RunProgressSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), indent=2) + "\n", encoding="utf-8")


def _format_message(
    phase: str,
    done: int,
    total: int,
    detail: str,
    *,
    step_label: str = "",
    step_elapsed_ms: int = 0,
    next_step_label: str = "",
) -> str:
    labels = {
        "starting": "Starting scrape",
        "scrape": "Scraping job boards",
        "validate": "Validating listings",
        "filter": "Filtering listings",
        "enrich": "Enriching jobs",
        "rank": "Ranking jobs",
        "done": "Scrape complete",
        "error": "Scrape failed",
        "cancelled": "Scrape cancelled",
    }
    label = step_label or labels.get(phase, phase.replace("_", " ").capitalize())
    if total > 0:
        line = f"{label} ({done}/{total})"
    else:
        line = label
    if detail:
        line = f"{line} — {detail}"
    if step_elapsed_ms >= 1000:
        line = f"{line} [{step_elapsed_ms // 1000}s]"
    if next_step_label:
        line = f"{line} · next: {next_step_label}"
    return line


class RunProgress:
    """Track scrape phase progress; optionally persist to disk for MCP polling."""

    def __init__(
        self,
        *,
        persist_path: Path | None = None,
        running: bool = False,
        on_change: Callable[[RunProgressSnapshot], None] | None = None,
        pid: int | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._persist_path = persist_path
        self._on_change = on_change
        self._phase = "idle"
        self._done = 0
        self._total = 0
        self._detail = ""
        self._running = running
        self._step_id = ""
        self._step_label = ""
        self._step_index = 0
        self._step_total = 0
        self._next_step_id = ""
        self._next_step_label = ""
        self._extra: dict[str, Any] = {}
        self._pid = pid
        self._cancelled = False
        self._run_started_mono: float | None = None
        self._run_started_at = ""
        self._step_started_mono: float | None = None
        self._step_started_at = ""
        self._plan: list[dict[str, str]] = [
            {"step_id": sid, "label": label, "status": "pending"}
            for sid, label in DEFAULT_SCRAPE_PLAN
        ]
        self._logs: list[dict[str, str]] = []

    def log(
        self,
        level: ScrapeLogLevel,
        message: str,
        *,
        step_id: str | None = None,
    ) -> None:
        """Append a line to the scrape activity log (persisted for the web UI)."""
        from agentzero.log_redaction import redact_secrets

        text = redact_secrets(message.strip())
        if not text:
            return
        with self._lock:
            self._append_log_locked(level, text, step_id=step_id or self._step_id)
        self._persist()

    def _append_log_locked(
        self,
        level: ScrapeLogLevel,
        message: str,
        *,
        step_id: str = "",
    ) -> None:
        self._logs.append(
            {
                "ts": _utc_now_iso(),
                "level": level,
                "message": message,
                "step_id": step_id,
            }
        )
        if len(self._logs) > SCRAPE_LOG_MAX:
            del self._logs[: len(self._logs) - SCRAPE_LOG_MAX]

    def begin_run(self, plan: Sequence[tuple[str, str]] | None = None) -> None:
        with self._lock:
            self._run_started_mono = time.monotonic()
            self._run_started_at = _utc_now_iso()
            self._cancelled = False
            self._logs = []
            if plan is not None:
                self._plan = [
                    {"step_id": sid, "label": label, "status": "pending"} for sid, label in plan
                ]
            self._append_log_locked("info", "Scrape run started")
        self._persist()

    def set_running(self, running: bool) -> None:
        with self._lock:
            self._running = running
            if not running and self._phase not in ("done", "error", "cancelled"):
                self._phase = "done"
        self._persist()

    def enter_step(
        self,
        step_id: str,
        *,
        phase: str | None = None,
        label: str | None = None,
        total: int = 0,
        done: int = 0,
        detail: str = "",
        step_index: int | None = None,
        next_step_id: str | None = None,
        next_step_label: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            if self._run_started_mono is None:
                self._run_started_mono = time.monotonic()
                self._run_started_at = _utc_now_iso()
            self._phase = phase or (step_id.split(".", 1)[0] if "." in step_id else step_id)
            self._step_id = step_id
            self._step_label = label or step_id
            self._total = max(0, total)
            self._done = max(0, min(done, self._total) if self._total else done)
            self._detail = detail
            self._step_total = self._total
            self._step_index = step_index if step_index is not None else (self._done + 1)
            self._step_started_mono = time.monotonic()
            self._step_started_at = _utc_now_iso()
            if next_step_id is not None:
                self._next_step_id = next_step_id
            if next_step_label is not None:
                self._next_step_label = next_step_label
            if extra:
                self._extra.update(dict(extra))
            self._mark_plan_active(step_id)
            line = self._step_label
            if detail:
                line = f"{line} — {detail}"
            self._append_log_locked("info", line, step_id=step_id)
        self._persist()

    def set_phase(
        self,
        phase: str,
        *,
        total: int = 0,
        done: int = 0,
        detail: str = "",
        step_id: str | None = None,
        label: str | None = None,
        next_step_id: str | None = None,
        next_step_label: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        sid = step_id or phase
        if label is None:
            label = _format_message(phase, done, total, "").split(" (")[0].split(" —")[0]
        self.enter_step(
            sid,
            phase=phase,
            label=label,
            total=total,
            done=done,
            detail=detail,
            next_step_id=next_step_id,
            next_step_label=next_step_label,
            extra=extra,
        )

    def step(self, *, detail: str = "", done: int | None = None) -> None:
        with self._lock:
            if done is not None:
                self._done = max(0, min(done, self._total) if self._total else done)
            elif self._total > 0:
                self._done = min(self._done + 1, self._total)
            else:
                self._done += 1
            if detail:
                self._detail = detail
                level: ScrapeLogLevel = "info"
                upper = detail.upper()
                if "FAILED" in detail:
                    level = "error"
                elif "WARNING" in upper or upper.startswith("WARN"):
                    level = "warn"
                self._append_log_locked(level, detail, step_id=self._step_id)
        self._persist()

    def finish(self, *, phase: str = "done", detail: str = "") -> None:
        with self._lock:
            self._phase = phase
            if self._total > 0:
                self._done = self._total
            self._detail = detail
            self._running = False
            self._mark_plan_done(self._step_id or phase)
            for entry in self._plan:
                if entry["status"] == "pending":
                    entry["status"] = "skipped"
            if detail:
                self._append_log_locked("info", detail, step_id=self._step_id)
        self._persist()

    def error(self, message: str) -> None:
        from agentzero.log_redaction import redact_secrets

        detail = redact_secrets(message)
        with self._lock:
            self._phase = "error"
            self._detail = detail
            self._running = False
            self._append_log_locked("error", detail, step_id=self._step_id)
        self._persist()

    def cancel(self, message: str = "Cancelled by operator") -> None:
        with self._lock:
            self._phase = "cancelled"
            self._detail = message
            self._running = False
            self._cancelled = True
            self._append_log_locked("warn", message, step_id=self._step_id)
        self._persist()

    def snapshot(self) -> RunProgressSnapshot:
        with self._lock:
            step_elapsed = _elapsed_ms(self._step_started_mono)
            run_elapsed = _elapsed_ms(self._run_started_mono)
            message = _format_message(
                self._phase,
                self._done,
                self._total,
                self._detail,
                step_label=self._step_label,
                step_elapsed_ms=step_elapsed,
                next_step_label=self._next_step_label,
            )
            return RunProgressSnapshot(
                phase=self._phase,
                done=self._done,
                total=self._total,
                detail=self._detail,
                message=message,
                running=self._running,
                step_id=self._step_id,
                step_label=self._step_label,
                step_index=self._step_index,
                step_total=self._step_total,
                step_elapsed_ms=step_elapsed,
                run_elapsed_ms=run_elapsed,
                run_started_at=self._run_started_at,
                step_started_at=self._step_started_at,
                next_step_id=self._next_step_id,
                next_step_label=self._next_step_label,
                plan=tuple(dict(e) for e in self._plan),
                extra=dict(self._extra),
                pid=self._pid,
                cancelled=self._cancelled,
                logs=tuple(dict(entry) for entry in self._logs),
            )

    def _mark_plan_active(self, step_id: str) -> None:
        phase_root = step_id.split(".", 1)[0]
        seen_active = False
        for entry in self._plan:
            sid = entry["step_id"]
            if sid == step_id or sid == phase_root:
                entry["status"] = "active"
                seen_active = True
            elif seen_active and entry["status"] == "active":
                entry["status"] = "pending"
            elif not seen_active and entry["status"] == "active":
                entry["status"] = "done"

    def _mark_plan_done(self, step_id: str) -> None:
        phase_root = step_id.split(".", 1)[0]
        for entry in self._plan:
            if entry["step_id"] == phase_root or entry["step_id"] == step_id:
                entry["status"] = "done"

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
        step_id: str | None = None,
    ) -> None:
        super().__init__(total, label=label)
        self._run_progress = run_progress
        self._phase = phase
        self._step_id = step_id or phase
        self._run_progress.enter_step(
            self._step_id,
            phase=phase,
            label=label,
            total=total,
            done=0,
        )

    def step(self, detail: str = "") -> None:
        super().step(detail)
        self._run_progress.step(detail=detail)

    def finish(self, summary: str = "") -> None:
        super().finish(summary)
        snap = self._run_progress.snapshot()
        self._run_progress.enter_step(
            self._step_id,
            phase=self._phase,
            label=snap.step_label,
            total=snap.total,
            done=snap.total,
            detail=summary or snap.detail,
        )


class ScrapeProgressLogHandler(logging.Handler):
    """Route warning/error log records from scrape modules into ``RunProgress``."""

    def __init__(self, progress: RunProgress) -> None:
        super().__init__(level=logging.WARNING)
        self._progress = progress

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: ScrapeLogLevel = "error" if record.levelno >= logging.ERROR else "warn"
            message = record.getMessage()
            if record.exc_info:
                import traceback

                from agentzero.log_redaction import redact_secrets

                message = redact_secrets(
                    message
                    + "\n"
                    + "".join(traceback.format_exception_only(record.exc_info[0], record.exc_info[1]))
                )
            self._progress.log(level, message)
        except Exception:  # noqa: BLE001 — logging must not break scrape
            self.handleError(record)


def attach_scrape_progress_logging(progress: RunProgress) -> ScrapeProgressLogHandler:
    """Attach a shared handler to scrape-related loggers; call ``detach`` when done."""
    handler = ScrapeProgressLogHandler(progress)
    handler.setFormatter(logging.Formatter("%(message)s"))
    for name in SCRAPE_LOG_LOGGER_NAMES:
        logging.getLogger(name).addHandler(handler)
    return handler


def detach_scrape_progress_logging(handler: ScrapeProgressLogHandler) -> None:
    for name in SCRAPE_LOG_LOGGER_NAMES:
        logging.getLogger(name).removeHandler(handler)


def merge_scrape_status(
    *,
    file_snap: RunProgressSnapshot | None,
    runner_snap: dict[str, object],
    process_alive: bool | None = None,
) -> dict[str, object]:
    """Prefer on-disk worker progress; overlay runner result fields."""
    base: dict[str, object] = dict(runner_snap)
    if file_snap is not None:
        base.update(file_snap.to_dict())
        base["scraped"] = runner_snap.get("scraped")
        base["leads"] = runner_snap.get("leads")
        base["errors"] = runner_snap.get("errors") or base.get("errors")
    if (
        process_alive is False
        and file_snap is not None
        and file_snap.running
        and not file_snap.cancelled
    ):
        base["running"] = False
        base["stale"] = True
        if base.get("phase") not in ("done", "error", "cancelled"):
            base["phase"] = "error"
            base["detail"] = str(base.get("detail") or "Worker exited unexpectedly")
            base["message"] = "Scrape failed — worker exited unexpectedly"
    return base
