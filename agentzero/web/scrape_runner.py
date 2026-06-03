"""Background scrape runs triggered from the web config page."""

from __future__ import annotations

import json
import multiprocessing
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentzero.ingest.search_profile import apply_search_profile, load_search_profile
from agentzero.loops.run_progress import (
    RunProgress,
    RunProgressSnapshot,
    load_scrape_progress_file,
    merge_scrape_status,
    save_scrape_progress_file,
    scrape_progress_path,
)
from agentzero.scrape.remote_policy import apply_remote_only_settings
from agentzero.web.search_targets import apply_operator_search_targets
from agentzero.web.search_titles import apply_operator_search_terms

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.storage.db import Database
    from agentzero.web.operator_config import OperatorScrapeConfig

_PROGRESS_POLL_SEC = 0.5


def scrape_worker_result_path(db_path: Path) -> Path:
    return db_path.parent / "scrape_worker_result.json"


def _write_worker_result(
    path: Path,
    *,
    message: str,
    scraped: int,
    leads: int,
    errors: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "message": message,
                "scraped": scraped,
                "leads": leads,
                "errors": list(errors),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _load_worker_result(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _scrape_worker(
    db_path: str,
    settings_dict: dict[str, Any],
    operator_dict: dict[str, Any] | None,
    progress_path: str,
    result_path: str,
) -> None:
    """Run scrape in a child process (Windows spawn-safe module-level entry)."""
    from agentzero.config import Settings
    from agentzero.storage.db import Database
    from agentzero.web.operator_config import OperatorScrapeConfig

    db = Database(Path(db_path))
    settings = Settings(_env_file=None, **settings_dict)
    operator = (
        OperatorScrapeConfig.model_validate(operator_dict) if operator_dict is not None else None
    )
    progress = RunProgress(
        persist_path=Path(progress_path),
        running=True,
        pid=os.getpid(),
    )
    from agentzero.loops.run_progress import (
        attach_scrape_progress_logging,
        detach_scrape_progress_logging,
    )

    log_handler = attach_scrape_progress_logging(progress)
    progress.begin_run()
    progress.enter_step(
        "starting.init",
        phase="starting",
        label="Starting scrape worker",
        total=1,
        done=0,
        next_step_id="starting.profile",
        next_step_label="Load search profile",
    )
    result_file = Path(result_path)

    try:
        message, scraped, leads, errors = _execute_scrape(
            db=db,
            settings=settings,
            operator=operator,
            progress=progress,
        )
        progress.finish(detail=message)
        for err in errors:
            progress.log("error", err)
        _write_worker_result(
            result_file,
            message=message,
            scraped=scraped,
            leads=leads,
            errors=errors,
        )
    except Exception as exc:  # noqa: BLE001 — surface to operator UI
        from agentzero.log_redaction import redact_secrets

        detail = redact_secrets(str(exc))
        progress.error(detail)
        _write_worker_result(
            result_file,
            message=f"Scrape failed: {detail}",
            scraped=0,
            leads=0,
            errors=[detail],
        )
    finally:
        detach_scrape_progress_logging(log_handler)
        progress.set_running(False)
        db.close()


@dataclass
class ScrapeRunState:
    running: bool = False
    last_message: str = ""
    last_scraped: int | None = None
    last_leads: int | None = None
    last_errors: list[str] = field(default_factory=list)
    phase: str = "idle"
    done: int = 0
    total: int = 0
    detail: str = ""
    step_id: str = ""
    step_label: str = ""
    step_elapsed_ms: int = 0
    run_elapsed_ms: int = 0
    next_step_id: str = ""
    next_step_label: str = ""
    pid: int | None = None
    stale: bool = False
    cancelled: bool = False
    plan: list[dict[str, str]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, str]] = field(default_factory=list)

    def apply_snapshot(self, snap: RunProgressSnapshot) -> None:
        self.phase = snap.phase
        self.done = snap.done
        self.total = snap.total
        self.detail = snap.detail
        self.step_id = snap.step_id
        self.step_label = snap.step_label
        self.step_elapsed_ms = snap.step_elapsed_ms
        self.run_elapsed_ms = snap.run_elapsed_ms
        self.next_step_id = snap.next_step_id
        self.next_step_label = snap.next_step_label
        self.pid = snap.pid
        self.stale = snap.stale
        self.cancelled = snap.cancelled
        self.plan = [dict(entry) for entry in snap.plan]
        self.extra = dict(snap.extra)
        self.logs = [dict(entry) for entry in snap.logs]
        if snap.message:
            self.last_message = snap.message
        self.running = snap.running

    def apply_progress(self, progress: RunProgress) -> None:
        self.apply_snapshot(progress.snapshot())

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "message": self.last_message,
            "phase": self.phase,
            "done": self.done,
            "total": self.total,
            "detail": self.detail,
            "scraped": self.last_scraped,
            "leads": self.last_leads,
            "errors": list(self.last_errors),
            "step_id": self.step_id,
            "step_label": self.step_label,
            "step_elapsed_ms": self.step_elapsed_ms,
            "run_elapsed_ms": self.run_elapsed_ms,
            "next_step_id": self.next_step_id,
            "next_step_label": self.next_step_label,
            "pid": self.pid,
            "stale": self.stale,
            "cancelled": self.cancelled,
            "plan": list(self.plan),
            "extra": dict(self.extra),
            "logs": list(self.logs),
        }


class ScrapeRunner:
    def __init__(self, *, db_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._db_path = db_path
        self._process: multiprocessing.Process | None = None
        self.state = ScrapeRunState()

    def _progress_path(self, db: Database) -> Path:
        return scrape_progress_path(self._db_path or db.path)

    def _process_alive(self) -> bool:
        proc = self._process
        return proc is not None and proc.is_alive()

    def reconcile(self, db: Database) -> None:
        """Clear stale running state when the worker process is gone."""
        path = self._progress_path(db)
        file_snap = load_scrape_progress_file(path)
        alive = self._process_alive()
        with self._lock:
            if file_snap is not None:
                self.state.apply_snapshot(file_snap)
            if not alive:
                self.state.running = False
                if file_snap is not None and file_snap.running and not file_snap.cancelled:
                    save_scrape_progress_file(
                        path,
                        RunProgressSnapshot(
                            phase="error",
                            detail="Worker exited unexpectedly (stale progress file)",
                            message="Scrape failed — worker exited unexpectedly",
                            running=False,
                            stale=True,
                            plan=file_snap.plan,
                            run_started_at=file_snap.run_started_at,
                            run_elapsed_ms=file_snap.run_elapsed_ms,
                        ),
                    )

    def start(
        self,
        *,
        db: Database,
        settings: Settings,
        operator: OperatorScrapeConfig | None,
    ) -> tuple[bool, str]:
        self.reconcile(db)
        with self._lock:
            if self.state.running or self._process_alive():
                return False, "A scrape is already running."
            self.state.running = True
            self.state.last_message = "Starting scrape…"
            self.state.last_errors = []
            self.state.phase = "starting"
            self.state.done = 0
            self.state.total = 1
            self.state.detail = ""

        persist = self._progress_path(db)
        result_path = scrape_worker_result_path(db.path)
        save_scrape_progress_file(
            persist,
            RunProgressSnapshot(
                phase="starting",
                done=0,
                total=1,
                detail="",
                message="Starting scrape…",
                running=True,
                step_id="starting.queue",
                step_label="Queueing scrape worker",
                logs=(),
            ),
        )
        if result_path.is_file():
            result_path.unlink()

        operator_dict = operator.model_dump(mode="json") if operator is not None else None
        settings_dict = settings.model_dump(mode="json")

        ctx = multiprocessing.get_context("spawn")
        process = ctx.Process(
            target=_scrape_worker,
            args=(
                str(db.path),
                settings_dict,
                operator_dict,
                str(persist),
                str(result_path),
            ),
            daemon=True,
            name="agentzero-web-scrape",
        )
        self._process = process
        process.start()

        thread = threading.Thread(
            target=self._watch_process,
            args=(db.path, process, persist, result_path),
            daemon=True,
            name="agentzero-web-scrape-watch",
        )
        thread.start()
        return True, "Scrape started in the background. Refresh jobs when it finishes."

    def stop(self, *, db: Database) -> tuple[bool, str]:
        """Terminate the background worker and mark progress cancelled."""
        path = self._progress_path(db)
        proc = self._process
        stopped = False
        if proc is not None and proc.is_alive():
            proc.terminate()
            proc.join(timeout=8)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=3)
            stopped = True

        from agentzero.loops.run_progress import scrape_log_entry

        snap = load_scrape_progress_file(path)
        logs = list(snap.logs) if snap else []
        logs.append(
            scrape_log_entry(
                "warn",
                "Stopped by operator",
                step_id=snap.step_id if snap else "cancelled",
            )
        )
        save_scrape_progress_file(
            path,
            RunProgressSnapshot(
                phase="cancelled",
                detail="Stopped by operator",
                message="Scrape cancelled",
                running=False,
                cancelled=True,
                plan=snap.plan if snap else (),
                run_started_at=snap.run_started_at if snap else "",
                run_elapsed_ms=snap.run_elapsed_ms if snap else 0,
                step_id=snap.step_id if snap else "cancelled",
                step_label="Cancelled",
                logs=tuple(logs),
            ),
        )
        with self._lock:
            self.state.running = False
            self.state.phase = "cancelled"
            self.state.last_message = "Scrape cancelled"
            self.state.detail = "Stopped by operator"
            self._process = None

        if stopped or (snap is not None and snap.running):
            return True, "Background scrape stopped."
        return False, "No background scrape was running."

    def _watch_process(
        self,
        db_path: Path,
        process: multiprocessing.Process,
        progress_path: Path,
        result_path: Path,
    ) -> None:
        try:
            while process.is_alive():
                snap = load_scrape_progress_file(progress_path)
                if snap is not None:
                    with self._lock:
                        self.state.apply_snapshot(snap)
                        self.state.running = True
                time.sleep(_PROGRESS_POLL_SEC)

            process.join(timeout=30)
            snap = load_scrape_progress_file(progress_path)
            result = _load_worker_result(result_path)
            with self._lock:
                if snap is not None:
                    self.state.apply_snapshot(snap)
                if result is not None:
                    self.state.last_message = str(result.get("message") or self.state.last_message)
                    scraped = result.get("scraped")
                    leads = result.get("leads")
                    self.state.last_scraped = int(scraped) if scraped is not None else None
                    self.state.last_leads = int(leads) if leads is not None else None
                    errors = result.get("errors")
                    if isinstance(errors, list):
                        self.state.last_errors = [str(e) for e in errors]
                self.state.running = False
        finally:
            with self._lock:
                self.state.running = False
            self._process = None

    def snapshot(self, *, db: Database | None = None) -> dict[str, Any]:
        file_snap = None
        if db is not None:
            file_snap = load_scrape_progress_file(self._progress_path(db))
        with self._lock:
            runner_snap = self.state.to_dict()
            if isinstance(runner_snap.get("errors"), list):
                runner_snap["errors"] = list(runner_snap["errors"])
            else:
                runner_snap["errors"] = []
        return merge_scrape_status(
            file_snap=file_snap,
            runner_snap=runner_snap,
            process_alive=self._process_alive() if db is not None else None,
        )


def _execute_scrape(
    *,
    db: Database,
    settings: Settings,
    operator: OperatorScrapeConfig | None,
    progress: RunProgress | None = None,
) -> tuple[str, int, int, list[str]]:
    from agentzero.ingest.resume import ingest_resume
    from agentzero.leads.session import run_lead_scrape
    from agentzero.llm.provider import build_llm_provider
    from agentzero.scrape.scrape_query_params import iter_scrape_queries
    from agentzero.web.operator_config import settings_for_scrape

    if progress is not None:
        progress.enter_step(
            "starting.profile",
            phase="starting",
            label="Load search profile",
            total=1,
            done=0,
            next_step_id="starting.llm",
            next_step_label="Load résumé and LLM",
        )

    snapshot = load_search_profile()
    if snapshot is None:
        if progress is not None:
            progress.error("No search profile found.")
        return (
            "No search profile found. Run scripts/smoke_test.py or a lead session first.",
            0,
            0,
            [],
        )

    cfg = apply_remote_only_settings(
        apply_operator_search_targets(
            apply_operator_search_terms(
                apply_search_profile(settings_for_scrape(settings, operator), snapshot),
                operator,
            ),
            operator,
        )
    )

    if progress is not None:
        queries = list(iter_scrape_queries(cfg))
        progress.enter_step(
            "starting.config",
            phase="starting",
            label="Apply scrape settings",
            total=1,
            done=1,
            detail=f"{len(queries)} search queries · {', '.join(cfg.scrape_browser_sites)}",
            next_step_id="scrape.boards",
            next_step_label="Scrape job boards",
            extra={
                "query_count": len(queries),
                "search_terms": list(cfg.search_terms),
                "boards": list(cfg.scrape_browser_sites),
                "results_wanted": cfg.results_wanted,
                "primary_query_only": cfg.scrape_primary_query_only,
            },
        )

    if progress is not None:
        progress.enter_step(
            "starting.llm",
            phase="starting",
            label="Load résumé and LLM",
            total=1,
            done=0,
            next_step_id="scrape.boards",
            next_step_label="Scrape job boards",
        )

    try:
        llm = build_llm_provider()
        resume_profile = ingest_resume(llm=llm, refresh_search=False)
    except ValueError as exc:
        if "Missing API key" in str(exc):
            if progress is not None:
                progress.error(str(exc))
            return (
                "Missing LLM API key (OPENAI_API_KEY or ANTHROPIC_API_KEY). "
                "Required for ranking during scrape.",
                0,
                0,
                [],
            )
        raise

    if progress is not None:
        progress.step(detail="profile ready")

    result = run_lead_scrape(db, cfg, llm=llm, profile=resume_profile, progress=progress)
    pipeline = result.pipeline
    msg = (
        f"Done: {pipeline.scraped} scraped, {result.lead_count} new lead(s). "
        "Review leads on the jobs list (status=lead)."
    )
    return msg, pipeline.scraped, result.lead_count, list(pipeline.errors)
