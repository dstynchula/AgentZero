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
    validate_browser_page_url,
    wait_for_html,
)
from agentzero.scrape.browser_linkedin import (
    _record_dedupe_key,
    build_linkedin_search_url,
    canonicalize_linkedin_record,
    page_has_job_results,
    page_needs_human,
    parse_linkedin_search_html,
)
from agentzero.scrape.scrape_query_params import iter_scrape_queries

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.scrape.location import ParsedLocation

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
        queries = list(iter_scrape_queries(self._settings))
        query_total = len(queries)
        pause = (
            not self._settings.scrape_browser_headless
            and self._settings.scrape_browser_pause_for_captcha
        )

        playwright = context = browser = None
        session_state: str | None = None
        has_markers: bool | None = None
        last_url = ""
        combined: list[RawRecord] = []
        seen: set[str] = set()
        total_parsed = 0
        total_filtered = 0
        last_snapshot: str | None = None
        login_required = False

        try:
            playwright, context, page, browser = launch_browser_page(
                self._settings, site="linkedin"
            )
            for query_index, (term, parsed) in enumerate(queries, start=1):
                if progress is not None and hasattr(progress, "enter_step"):
                    next_id = (
                        f"scrape.linkedin.query_{query_index + 1}"
                        if query_index < query_total
                        else "validate.batch"
                    )
                    next_label = (
                        f"LinkedIn: {queries[query_index][0]}"
                        if query_index < query_total
                        else "Validate listings"
                    )
                    progress.enter_step(
                        f"scrape.linkedin.query_{query_index}",
                        phase="scrape",
                        label=f"LinkedIn search ({query_index}/{query_total})",
                        total=query_total,
                        done=query_index - 1,
                        detail=term,
                        step_index=query_index,
                        next_step_id=next_id,
                        next_step_label=next_label,
                        extra={
                            "board": "linkedin",
                            "term": term,
                            "query_index": query_index,
                            "query_total": query_total,
                        },
                    )
                batch, stats, meta = self._search_query_on_page(
                    page,
                    term=term,
                    parsed=parsed,
                    pause=pause,
                )
                last_url = meta.get("url", last_url) or last_url
                session_state = meta.get("session_state") or session_state
                has_markers = meta.get("has_job_markers")
                last_snapshot = meta.get("html_snapshot") or last_snapshot
                if meta.get("login_required"):
                    login_required = True
                if meta.get("error"):
                    return LinkedInSearchResult(
                        url=last_url,
                        error=str(meta["error"]),
                        session_state=session_state,
                        has_job_markers=has_markers,
                        login_required=login_required,
                    )
                total_parsed += stats.parsed_raw
                total_filtered += stats.after_title_filter
                for record in batch:
                    canonical = canonicalize_linkedin_record(record)
                    key = _record_dedupe_key(canonical)
                    if key in seen:
                        continue
                    seen.add(key)
                    combined.append(canonical)
                if progress is not None and hasattr(progress, "step"):
                    progress.step(
                        detail=f"{term}: {len(batch)} parsed, {len(combined)} unique so far",
                        done=query_index,
                    )

            if (
                self._settings.scrape_session_preflight
                and login_required
                and not combined
            ):
                from agentzero.scrape.browser_session import (
                    SessionState,
                    session_status_message,
                )

                print(
                    session_status_message("linkedin", SessionState.LOGIN_REQUIRED),
                    file=sys.stderr,
                )
                return LinkedInSearchResult(
                    url=last_url,
                    login_required=True,
                    session_state=session_state or SessionState.LOGIN_REQUIRED.value,
                    has_job_markers=has_markers,
                )

            return LinkedInSearchResult(
                records=combined[: self._settings.results_wanted],
                url=last_url,
                parsed_raw=total_parsed or None,
                after_title_filter=total_filtered or None,
                session_state=session_state,
                has_job_markers=has_markers,
                html_snapshot=last_snapshot,
                login_required=login_required and not combined,
            )
        except Exception as exc:
            from agentzero.log_redaction import redact_secrets

            log.warning("%s search failed: %s", _DISPLAY, redact_secrets(str(exc)))
            return LinkedInSearchResult(
                url=last_url,
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

    def _search_query_on_page(
        self,
        page: object,
        *,
        term: str,
        parsed: ParsedLocation,
        pause: bool,
    ) -> tuple[list[RawRecord], _ParseStats, dict[str, object]]:
        """Run one search URL on an open page; return records + telemetry meta."""
        from agentzero.scrape.browser_session import (
            SessionState,
            classify_session,
        )

        url = build_linkedin_search_url(term=term, parsed=parsed)
        meta: dict[str, object] = {"url": url}
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)  # type: ignore[union-attr]
        if not validate_browser_page_url(page):
            meta["error"] = "invalid_page_url"
            return [], _ParseStats(), meta

        click_consent_buttons(page, _LINKEDIN_CONSENT)
        _prepare_search_page(page)
        html = wait_for_html(page, predicate=page_has_job_results, timeout_ms=30_000)
        has_markers = page_has_job_results(html)
        meta["has_job_markers"] = has_markers

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
        meta["has_job_markers"] = has_markers
        meta["html_snapshot"] = post_html[:500_000]

        post_state = classify_session("linkedin", post_html, page.url)  # type: ignore[union-attr]
        meta["session_state"] = post_state.value

        records, stats = self._parse_with_retry(
            page, url=url, term=term, parsed_remote=parsed.is_remote
        )
        if records and post_state is not SessionState.READY:
            meta["session_state"] = SessionState.READY.value
        elif post_state is SessionState.LOGIN_REQUIRED and not records:
            meta["login_required"] = True

        return records, stats, meta

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
