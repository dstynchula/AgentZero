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
_SCROLL_SELECTORS = (
    ".jobs-search-results-list",
    ".scaffold-layout__list",
    "[data-test-id='job-search-results-list']",
)


@dataclass(slots=True)
class LinkedInSearchResult:
    records: list[RawRecord] = field(default_factory=list)
    url: str = ""
    login_required: bool = False
    error: str | None = None
    parsed_raw: int | None = None
    after_title_filter: int | None = None
    session_state: str | None = None
    has_job_markers: bool | None = None
    html_snapshot: str | None = None


@dataclass(slots=True)
class _ParseStats:
    parsed_raw: int = 0
    after_title_filter: int = 0


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

        playwright = context = browser = None
        session_state: str | None = None
        has_markers: bool | None = None
        try:
            playwright, context, page, browser = launch_browser_page(
                self._settings, site="linkedin"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            if not validate_browser_page_url(page):
                return LinkedInSearchResult(url=url, error="invalid_page_url")

            click_consent_buttons(page, _LINKEDIN_CONSENT)
            _prepare_search_page(page)
            html = wait_for_html(page, predicate=page_has_job_results, timeout_ms=30_000)
            has_markers = page_has_job_results(html)

            def _reload_search(p: object) -> None:
                p.goto(url, wait_until="domcontentloaded", timeout=60_000)  # type: ignore[union-attr]
                if validate_browser_page_url(p):  # type: ignore[arg-type]
                    click_consent_buttons(p, _LINKEDIN_CONSENT)
                    _prepare_search_page(p)

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

            post_html = _safe_page_content(page)
            has_markers = page_has_job_results(post_html)
            from agentzero.scrape.browser_session import (
                SessionState,
                classify_session,
                session_status_message,
            )

            post_state = classify_session("linkedin", post_html, page.url)
            session_state = post_state.value
            if self._settings.scrape_session_preflight and post_state is SessionState.LOGIN_REQUIRED:
                print(session_status_message("linkedin", post_state), file=sys.stderr)
                log.warning("%s: login required after search load", _DISPLAY)
                return LinkedInSearchResult(
                    url=url,
                    login_required=True,
                    session_state=session_state,
                    has_job_markers=has_markers,
                )

            records, stats = self._parse_with_retry(
                page, url=url, term=term, parsed_remote=parsed.is_remote
            )
            snapshot = post_html[:500_000]
            return LinkedInSearchResult(
                records=records[: self._settings.results_wanted],
                url=url,
                parsed_raw=stats.parsed_raw,
                after_title_filter=stats.after_title_filter,
                session_state=session_state,
                has_job_markers=has_markers,
                html_snapshot=snapshot,
            )
        except Exception as exc:
            from agentzero.log_redaction import redact_secrets

            log.warning("%s search failed: %s", _DISPLAY, redact_secrets(str(exc)))
            return LinkedInSearchResult(
                url=url,
                error=redact_secrets(str(exc)),
                session_state=session_state,
                has_job_markers=has_markers,
            )
        finally:
            close_browser_session(
                playwright,
                context,
                self._settings,
                site="linkedin",
                browser=browser,
            )

    def get_job_details_html(self, job_url: str) -> str | None:
        """Fetch a single job posting page (for MCP detail tool)."""
        playwright = context = browser = None
        try:
            playwright, context, page, browser = launch_browser_page(
                self._settings, site="linkedin"
            )
            page.goto(job_url, wait_until="domcontentloaded", timeout=60_000)
            if not validate_browser_page_url(page):
                return None
            click_consent_buttons(page, _LINKEDIN_CONSENT)
            return _safe_page_content(page)
        except Exception as exc:
            from agentzero.log_redaction import redact_secrets

            log.warning("LinkedIn detail fetch failed: %s", redact_secrets(str(exc)))
            return None
        finally:
            close_browser_session(
                playwright,
                context,
                self._settings,
                site="linkedin",
                browser=browser,
            )

    def _parse_with_retry(
        self,
        page: object,
        *,
        url: str,
        term: str,
        parsed_remote: bool,
    ) -> tuple[list[RawRecord], _ParseStats]:
        term_key = term
        last_stats = _ParseStats()

        def _parse_current() -> tuple[list[RawRecord], _ParseStats]:
            html = _safe_page_content(page)
            records = list(parse_linkedin_search_html(html, source="linkedin"))
            if not records:
                html = wait_for_html(page, predicate=page_has_job_results, timeout_ms=15_000)
                records = list(parse_linkedin_search_html(html, source="linkedin"))
            if parsed_remote:
                from agentzero.scrape.remote_policy import apply_remote_search_trust_to_record

                for record in records:
                    apply_remote_search_trust_to_record(record, remote_search=True)
            parsed_raw = len(records)
            from agentzero.scrape.title_filter import title_matches_search

            filtered = [
                r for r in records if title_matches_search(str(r.get("title", "")), [term_key])
            ]
            return filtered, _ParseStats(
                parsed_raw=parsed_raw,
                after_title_filter=len(filtered),
            )

        records, last_stats = _parse_current()
        retries = 0
        while not records and retries < _MAX_EMPTY_RETRIES:
            retries += 1
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)  # type: ignore[union-attr]
                click_consent_buttons(page, _LINKEDIN_CONSENT)
                _prepare_search_page(page)
                wait_for_html(page, predicate=page_has_job_results, timeout_ms=20_000)
            except Exception:
                break
            records, last_stats = _parse_current()
        return records, last_stats


def _safe_page_content(page: object, *, retries: int = 4) -> str:
    """Read HTML; retry when Playwright reports in-flight navigation."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return page.content()  # type: ignore[union-attr]
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            if "navigating" not in msg and "changing the content" not in msg:
                raise
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5_000)  # type: ignore[union-attr]
            except Exception:
                pass
            try:
                page.wait_for_timeout(400 * (attempt + 1))  # type: ignore[union-attr]
            except Exception:
                break
    if last_exc is not None:
        raise last_exc
    return page.content()  # type: ignore[union-attr]


def _prepare_search_page(page: object) -> None:
    """Wait for network settle and scroll results list so lazy cards load."""
    try:
        page.wait_for_load_state("networkidle", timeout=12_000)  # type: ignore[union-attr]
    except Exception:
        pass
    for selector in _SCROLL_SELECTORS:
        try:
            loc = page.locator(selector).first  # type: ignore[union-attr]
            if loc.is_visible(timeout=2_000):
                loc.evaluate("el => { el.scrollTop = el.scrollHeight; }")
                page.wait_for_timeout(800)  # type: ignore[union-attr]
                return
        except Exception:
            continue
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")  # type: ignore[union-attr]
        page.wait_for_timeout(500)  # type: ignore[union-attr]
    except Exception:
        pass


def _default_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""
