"""Background scrape runs triggered from the web config page."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agentzero.ingest.search_profile import apply_search_profile, load_search_profile
from agentzero.scrape.remote_policy import apply_remote_only_settings
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "message": self.last_message,
            "scraped": self.last_scraped,
            "leads": self.last_leads,
            "errors": list(self.last_errors),
        }


class ScrapeRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
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

        thread = threading.Thread(
            target=self._run,
            args=(db, settings, operator),
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
    ) -> None:
        try:
            message, scraped, leads, errors = _execute_scrape(
                db=db,
                settings=settings,
                operator=operator,
            )
            with self._lock:
                self.state.last_message = message
                self.state.last_scraped = scraped
                self.state.last_leads = leads
                self.state.last_errors = errors
        except Exception as exc:  # noqa: BLE001 — surface to operator UI
            with self._lock:
                self.state.last_message = f"Scrape failed: {exc}"
                self.state.last_errors = [str(exc)]
        finally:
            with self._lock:
                self.state.running = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.state.to_dict()


def _execute_scrape(
    *,
    db: Database,
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> tuple[str, int, int, list[str]]:
    from agentzero.ingest.resume import ingest_resume
    from agentzero.leads.session import run_lead_scrape
    from agentzero.llm.provider import build_llm_provider
    from agentzero.web.operator_config import settings_for_scrape

    snapshot = load_search_profile()
    if snapshot is None:
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

    try:
        llm = build_llm_provider()
        resume_profile = ingest_resume(llm=llm, refresh_search=False)
    except ValueError as exc:
        if "Missing API key" in str(exc):
            return (
                "Missing LLM API key (OPENAI_API_KEY or ANTHROPIC_API_KEY). "
                "Required for ranking during scrape.",
                0,
                0,
                [],
            )
        raise

    result = run_lead_scrape(db, cfg, llm=llm, profile=resume_profile)
    pipeline = result.pipeline
    msg = (
        f"Done: {pipeline.scraped} scraped, {result.lead_count} new lead(s). "
        "Review leads on the jobs list (status=lead)."
    )
    return msg, pipeline.scraped, result.lead_count, list(pipeline.errors)
