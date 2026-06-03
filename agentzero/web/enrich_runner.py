"""Background batch enrich runs triggered from the jobs list."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentzero.loops.run_progress import (
    RunProgress,
    RunProgressSnapshot,
    enrich_progress_path,
    load_scrape_progress_file,
    save_scrape_progress_file,
)

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.storage.db import Database


@dataclass
class EnrichRunState:
    running: bool = False
    last_message: str = ""
    last_errors: list[str] = field(default_factory=list)
    phase: str = "idle"
    done: int = 0
    total: int = 0
    detail: str = ""
    step_id: str = ""
    step_label: str = ""
    logs: list[dict[str, str]] = field(default_factory=list)

    def apply_snapshot(self, snap: RunProgressSnapshot) -> None:
        self.phase = snap.phase
        self.done = snap.done
        self.total = snap.total
        self.detail = snap.detail
        self.last_message = snap.message or self.last_message
        self.step_id = snap.step_id
        self.step_label = snap.step_label
        self.logs = [dict(entry) for entry in snap.logs]

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "message": self.last_message,
            "phase": self.phase,
            "done": self.done,
            "total": self.total,
            "detail": self.detail,
            "errors": list(self.last_errors),
            "step_id": self.step_id,
            "step_label": self.step_label,
            "logs": list(self.logs),
        }


class EnrichRunner:
    def __init__(self, *, db_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._db_path = db_path
        self._thread: threading.Thread | None = None
        self.state = EnrichRunState()

    def _progress_path(self, db: Database) -> Path:
        return enrich_progress_path(self._db_path or db.path)

    def _thread_alive(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def reconcile(self, db: Database) -> None:
        path = self._progress_path(db)
        file_snap = load_scrape_progress_file(path)
        with self._lock:
            if file_snap is not None:
                self.state.apply_snapshot(file_snap)
            if not self._thread_alive():
                self.state.running = False

    def start(
        self,
        *,
        db: Database,
        settings: Settings,
        job_ids: list[str],
    ) -> tuple[bool, str]:
        self.reconcile(db)
        if not job_ids:
            return False, "No jobs selected for enrich."
        with self._lock:
            if self.state.running or self._thread_alive():
                return False, "An enrich batch is already running."
            self.state.running = True
            self.state.last_message = "Starting enrich batch…"
            self.state.last_errors = []
            self.state.phase = "starting"
            self.state.done = 0
            self.state.total = len(job_ids)
            self.state.detail = ""

        persist = self._progress_path(db)
        save_scrape_progress_file(
            persist,
            RunProgressSnapshot(
                phase="starting",
                done=0,
                total=len(job_ids),
                detail="",
                message="Starting enrich batch…",
                running=True,
                step_id="enrich.queue",
                step_label="Queueing enrich worker",
                logs=(),
            ),
        )

        thread = threading.Thread(
            target=self._run,
            args=(db.path, settings.model_dump(mode="json"), list(job_ids), persist),
            daemon=True,
            name="agentzero-web-enrich",
        )
        self._thread = thread
        thread.start()
        return True, f"Enriching {len(job_ids)} job(s) in the background."

    def stop(self, *, db: Database) -> tuple[bool, str]:
        path = self._progress_path(db)
        snap = load_scrape_progress_file(path)
        save_scrape_progress_file(
            path,
            RunProgressSnapshot(
                phase="cancelled",
                detail="Stop requested",
                message="Enrich cancelled",
                running=False,
                cancelled=True,
                plan=snap.plan if snap else (),
                run_started_at=snap.run_started_at if snap else "",
                run_elapsed_ms=snap.run_elapsed_ms if snap else 0,
                step_id="cancelled",
                step_label="Cancelled",
                logs=snap.logs if snap else (),
            ),
        )
        with self._lock:
            self.state.running = False
            self.state.phase = "cancelled"
            self.state.last_message = "Enrich cancelled"
        return True, "Enrich batch marked cancelled."

    def _run(
        self,
        db_path: Path,
        settings_dict: dict[str, Any],
        job_ids: list[str],
        progress_path: Path,
    ) -> None:
        from agentzero.config import Settings
        from agentzero.enrich.batch import run_enrich_batch
        from agentzero.loops.run_progress import (
            attach_scrape_progress_logging,
            detach_scrape_progress_logging,
        )
        from agentzero.storage.db import Database

        db = Database(db_path)
        settings = Settings(_env_file=None, **settings_dict)
        progress = RunProgress(persist_path=progress_path, running=True)
        log_handler = attach_scrape_progress_logging(progress)
        progress.begin_run()
        progress.enter_step(
            "enrich.batch",
            phase="enrich",
            label="Enrich selected jobs",
            total=len(job_ids),
            done=0,
        )

        try:
            result = run_enrich_batch(
                db,
                job_ids,
                settings=settings,
                max_workers=settings.enrich_max_concurrency,
                fetch_detail=settings.enrich_fetch_details,
                glassdoor_lookup=settings.enrich_glassdoor_lookup,
                web_search=settings.enrich_web_search,
                allow_browser=True,
                browser_delay_seconds=settings.enrich_delay_seconds,
            )
            message = (
                f"Enrich complete: {result.improved}/{result.total} improved, "
                f"{result.failed} failed."
            )
            progress.finish(detail=message)
            with self._lock:
                self.state.last_message = message
                if result.failed:
                    self.state.last_errors = [f"{result.failed} job(s) failed enrich"]
        except Exception as exc:
            progress.finish(detail=str(exc))
            with self._lock:
                self.state.last_message = f"Enrich failed: {exc}"
                self.state.last_errors = [str(exc)]
        finally:
            detach_scrape_progress_logging(log_handler)
            db.close()
            with self._lock:
                self.state.running = False
                self._thread = None

    def snapshot(self, *, db: Database | None = None) -> dict[str, Any]:
        file_snap = None
        if db is not None:
            self.reconcile(db)
            file_snap = load_scrape_progress_file(self._progress_path(db))
        with self._lock:
            runner_snap = self.state.to_dict()
        if file_snap is not None:
            merged = file_snap.to_dict()
            merged["errors"] = runner_snap.get("errors") or merged.get("errors")
            merged["running"] = bool(merged.get("running")) and self._thread_alive()
            return merged
        return runner_snap
