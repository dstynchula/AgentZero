"""Probe a job-board browser profile and classify session health."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentzero.scrape.browser_session import (
    SESSION_EXIT_CODES,
    SessionState,
    classify_session,
)

if TYPE_CHECKING:
    from agentzero.config import Settings


@dataclass
class SessionProbeResult:
    site: str
    state: SessionState
    url: str
    listing_count: int = 0
    error: str | None = None

    @property
    def exit_code(self) -> int:
        if self.error:
            return 3
        return SESSION_EXIT_CODES.get(self.state, 3)


def probe_browser_session(settings: Settings, site: str) -> SessionProbeResult:
    """Open profile, navigate to job search, classify session."""
    from agentzero.scrape.browser_board import SITE_CONFIGS
    from agentzero.scrape.browser_common import (
        close_browser_session,
        launch_browser_page,
        primary_scrape_query,
        validate_browser_page_url,
        wait_for_html,
    )

    key = site.strip().lower()
    if key not in SITE_CONFIGS:
        return SessionProbeResult(site=key, state=SessionState.UNKNOWN, url="", error=f"unknown site: {site}")

    _display, _needs_human, has_results, build_url, parse_html, _consent = SITE_CONFIGS[key]
    term, parsed = primary_scrape_query(settings)
    url = build_url(term=term, parsed=parsed)

    playwright = context = None
    try:
        playwright, context, page = launch_browser_page(settings, site=key)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if not validate_browser_page_url(page):
            return SessionProbeResult(
                site=key,
                state=SessionState.UNKNOWN,
                url=page.url,
                error="blocked URL after navigation",
            )
        html = wait_for_html(page, predicate=has_results, timeout_ms=15_000)
        if not html:
            html = page.content()
        current_url = page.url
        state = classify_session(key, html, current_url)
        records = parse_html(html, source=key) if state is SessionState.READY else []
        if records and state is not SessionState.READY:
            state = SessionState.READY
        return SessionProbeResult(
            site=key,
            state=state,
            url=current_url,
            listing_count=len(records),
        )
    except Exception as exc:
        return SessionProbeResult(site=key, state=SessionState.UNKNOWN, url=url, error=str(exc))
    finally:
        close_browser_session(playwright, context, settings, site=key)
