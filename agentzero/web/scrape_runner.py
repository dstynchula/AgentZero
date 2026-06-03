"""Background scrape runs triggered from the web config page."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentzero.ingest.search_profile import apply_search_profile, load_search_profile
from agentzero.loops.run_progress import RunProgress, RunProgressSnapshot, scrape_progress_path
from agentzero.scrape.remote_policy import apply_remote_only_settings
from agentzero.web.search_targets import apply_operator_search_targets
from agentzero.web.search_titles import apply_operator_search_terms

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.storage.db import Database
    from agentzero.web.operator_config import OperatorScrapeConfig


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

        def sync_progress(snap: RunProgressSnapshot) -> None:
            with self._lock:
                self.state.apply_snapshot(snap)

        progress = RunProgress(
            persist_path=persist,
            running=True,
            on_change=sync_progress,
        )
        progress.set_phase("starting", total=1, done=0)

        thread = threading.Thread(
            target=self._run,
            args=(db, settings, operator, progress),
            daemon=True,
            name="agentzero-web-scrape",
        )
        thread.start()
        return True, "Scrape started in the background. Refresh jobs when it finishes."

    def _run(
        self,
        db: Database,
        settings: Settings,
        operator: OperatorScrapeConfig | None,
        progress: RunProgress,
    ) -> None:
        try:
            message, scraped, leads, errors = _execute_scrape(
                db=db,
                settings=settings,
                operator=operator,
                progress=progress,
            )
            progress.finish(detail=message)
            with self._lock:
                self.state.apply_progress(progress)
                self.state.last_message = message
                self.state.last_scraped = scraped
                self.state.last_leads = leads
                self.state.last_errors = errors
        except Exception as exc:  # noqa: BLE001 — surface to operator UI
            progress.error(str(exc))
            with self._lock:
                self.state.apply_progress(progress)
                self.state.last_message = f"Scrape failed: {exc}"
                self.state.last_errors = [str(exc)]
        finally:
            with self._lock:
                self.state.running = False
            progress.set_running(False)

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
        apply_operator_search_targets(
            apply_operator_search_terms(
                apply_search_profile(settings_for_scrape(settings, operator), snapshot),
                operator,
            ),
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
