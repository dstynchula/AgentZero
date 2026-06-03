"""LinkedIn job search and detail fetch via Playwright (shared by board + MCP)."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentzero.models import RawRecord
from agentzero.scrape.browser_common import (
    click_consent_buttons,
    close_browser_session,
    launch_browser_page,
    maybe_wait_for_human,
    primary_scrape_query,
    validate_browser_page_url,
    wait_for_html,
)
from agentzero.scrape.browser_linkedin import (
    build_linkedin_search_url,
    page_has_job_results,
    page_needs_human,
    parse_linkedin_search_html,
)

if TYPE_CHECKING:
    from agentzero.config import Settings

log = logging.getLogger(__name__)

_LINKEDIN_CONSENT = ('button:has-text("Accept")',)
_DISPLAY = "LinkedIn"
_MAX_EMPTY_RETRIES = 1


@dataclass(slots=True)
class LinkedInSearchResult:
    records: list[RawRecord] = field(default_factory=list)
    url: str = ""
    login_required: bool = False
    error: str | None = None
    # Debug telemetry (populated by search(); omitted from MCP payloads unless requested)
    parsed_raw: int | None = None
    after_title_filter: int | None = None
    session_state: str | None = None
    has_job_markers: bool | None = None


class LinkedInJobsService:
    """Playwright-backed LinkedIn search with session preflight and one reload on empty parse."""

    def __init__(
        self,
        settings: Settings,
        *,
        input_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._settings = settings
        self._input_fn = input_fn or _default_input

    def search(self, *, progress: object | None = None) -> LinkedInSearchResult:
        _ = progress
        term, parsed = primary_scrape_query(self._settings)
        url = build_linkedin_search_url(term=term, parsed=parsed)
        pause = (
            not self._settings.scrape_browser_headless
            and self._settings.scrape_browser_pause_for_captcha
        )

        playwright = context = None
        try:
            playwright, context, page = launch_browser_page(self._settings, site="linkedin")
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            if not validate_browser_page_url(page):
                return LinkedInSearchResult(url=url, error="invalid_page_url")

            if self._settings.scrape_session_preflight:
                from agentzero.scrape.browser_session import (
                    SessionState,
                    classify_session,
                    session_status_message,
                )

                pre_html = page.content()
                pre_state = classify_session("linkedin", pre_html, page.url)
                if pre_state is SessionState.LOGIN_REQUIRED:
                    print(session_status_message("linkedin", pre_state), file=sys.stderr)
                    log.warning("%s: preflight login required", _DISPLAY)
                    return LinkedInSearchResult(url=url, login_required=True)

            click_consent_buttons(page, _LINKEDIN_CONSENT)
            html = wait_for_html(page, predicate=page_has_job_results, timeout_ms=30_000)

            def _reload_search(p: object) -> None:
                p.goto(url, wait_until="domcontentloaded", timeout=60_000)  # type: ignore[union-attr]
                if validate_browser_page_url(p):  # type: ignore[arg-type]
                    click_consent_buttons(p, _LINKEDIN_CONSENT)

            maybe_wait_for_human(
                page,
                site=_DISPLAY,
                html=html,
                needs_human=page_needs_human,
                input_fn=self._input_fn,
                pause_enabled=pause,
                has_results=page_has_job_results,
                after_prompt=_reload_search if pause else None,
            )

            records = self._parse_with_retry(page, url=url, term=term, parsed_remote=parsed.is_remote)
            return LinkedInSearchResult(
                records=records[: self._settings.results_wanted],
                url=url,
            )
        except Exception as exc:
            from agentzero.log_redaction import redact_secrets

            log.warning("%s search failed: %s", _DISPLAY, redact_secrets(str(exc)))
            return LinkedInSearchResult(url=url, error=redact_secrets(str(exc)))
        finally:
            close_browser_session(playwright, context, self._settings, site="linkedin")

    def get_job_details_html(self, job_url: str) -> str | None:
        """Fetch a single job posting page (for MCP detail tool)."""
        playwright = context = None
        try:
            playwright, context, page = launch_browser_page(self._settings, site="linkedin")
            page.goto(job_url, wait_until="domcontentloaded", timeout=60_000)
            if not validate_browser_page_url(page):
                return None
            click_consent_buttons(page, _LINKEDIN_CONSENT)
            return page.content()
        except Exception as exc:
            from agentzero.log_redaction import redact_secrets

            log.warning("LinkedIn detail fetch failed: %s", redact_secrets(str(exc)))
            return None
        finally:
            close_browser_session(playwright, context, self._settings, site="linkedin")

    def _parse_with_retry(
        self,
        page: object,
        *,
        url: str,
        term: str,
        parsed_remote: bool,
    ) -> list[RawRecord]:
        term_key = term

        def _parse_current() -> list[RawRecord]:
            html = page.content()  # type: ignore[union-attr]
            records = list(parse_linkedin_search_html(html, source="linkedin"))
            if not records:
                html = wait_for_html(page, predicate=page_has_job_results, timeout_ms=15_000)
                records = list(parse_linkedin_search_html(html, source="linkedin"))
            if parsed_remote:
                from agentzero.scrape.remote_policy import apply_remote_search_trust_to_record

                for record in records:
                    apply_remote_search_trust_to_record(record, remote_search=True)
            from agentzero.scrape.title_filter import title_matches_search

            return [r for r in records if title_matches_search(str(r.get("title", "")), [term_key])]

        records = _parse_current()
        retries = 0
        while not records and retries < _MAX_EMPTY_RETRIES:
            retries += 1
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)  # type: ignore[union-attr]
                click_consent_buttons(page, _LINKEDIN_CONSENT)
                wait_for_html(page, predicate=page_has_job_results, timeout_ms=20_000)
            except Exception:
                break
            records = _parse_current()
        return records


def _default_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""
