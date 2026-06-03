"""Background scrape runs triggered from the web config page."""

from __future__ import annotations

import json
import multiprocessing
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
    save_scrape_progress_file,
    scrape_progress_path,
)
from agentzero.scrape.remote_policy import apply_remote_only_settings
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
    progress = RunProgress(persist_path=Path(progress_path), running=True)
    progress.set_phase("starting", total=1, done=0)
    result_file = Path(result_path)

    try:
        message, scraped, leads, errors = _execute_scrape(
            db=db,
            settings=settings,
            operator=operator,
            progress=progress,
        )
        progress.finish(detail=message)
        _write_worker_result(
            result_file,
            message=message,
            scraped=scraped,
            leads=leads,
            errors=errors,
        )
    except Exception as exc:  # noqa: BLE001 — surface to operator UI
        progress.error(str(exc))
        _write_worker_result(
            result_file,
            message=f"Scrape failed: {exc}",
            scraped=0,
            leads=0,
            errors=[str(exc)],
        )
    finally:
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

    def apply_snapshot(self, snap: RunProgressSnapshot) -> None:
        self.phase = snap.phase
        self.done = snap.done
        self.total = snap.total
        self.detail = snap.detail
        if snap.message:
            self.last_message = snap.message

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
        }


class ScrapeRunner:
    def __init__(self, *, db_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._db_path = db_path
        self._process: multiprocessing.Process | None = None
        self.state = ScrapeRunState()

    def start(
        self,
        *,
        db: Database,
        settings: Settings,
        operator: OperatorScrapeConfig | None,
    ) -> tuple[bool, str]:
        with self._lock:
            if self.state.running:
                return False, "A scrape is already running."
            self.state.running = True
            self.state.last_message = "Starting scrape…"
            self.state.last_errors = []
            self.state.phase = "starting"
            self.state.done = 0
            self.state.total = 1
            self.state.detail = ""

        persist = scrape_progress_path(db.path)
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
            args=(process, persist, result_path),
            daemon=True,
            name="agentzero-web-scrape-watch",
        )
        thread.start()
        return True, "Scrape started in the background. Refresh jobs when it finishes."

    def _watch_process(
        self,
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
        finally:
            with self._lock:
                self.state.running = False
            self._process = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.state.to_dict()


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
    from agentzero.web.operator_config import settings_for_scrape

    if progress is not None:
        progress.set_phase("starting", total=1, done=0)

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
        apply_operator_search_terms(
            apply_search_profile(settings_for_scrape(settings, operator), snapshot),
            operator,
        )
    )

    if progress is not None:
        progress.step(detail="loading profile")

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

    result = run_lead_scrape(db, cfg, llm=llm, profile=resume_profile, progress=progress)
    pipeline = result.pipeline
    msg = (
        f"Done: {pipeline.scraped} scraped, {result.lead_count} new lead(s). "
        "Review leads on the jobs list (status=lead)."
    )
    return msg, pipeline.scraped, result.lead_count, list(pipeline.errors)
