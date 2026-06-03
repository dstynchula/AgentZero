"""Generic Playwright job-board fetcher (single query per run)."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from agentzero.models import RawRecord
from agentzero.scrape.base import JobSource
from agentzero.scrape.browser_common import (
    click_consent_buttons,
    close_browser_session,
    launch_browser_page,
    maybe_wait_for_human,
    primary_scrape_query,
    validate_browser_page_url,
    wait_for_html,
)

if TYPE_CHECKING:
    from agentzero.config import Settings

log = logging.getLogger(__name__)

SiteConfig = tuple[
    str,
    Callable[[str, str], bool],
    Callable[[str, str], bool],
    Callable[..., str],
    Callable[..., list[RawRecord]],
    tuple[str, ...],
]


def _indeed_cfg() -> SiteConfig:
    from agentzero.scrape.browser_indeed import (
        build_indeed_search_url,
        page_has_job_results,
        page_needs_human,
        parse_indeed_search_html,
    )

    return (
        "Indeed",
        page_needs_human,
        page_has_job_results,
        build_indeed_search_url,
        parse_indeed_search_html,
        ("button#onetrust-accept-btn-handler",),
    )


def _linkedin_cfg() -> SiteConfig:
    from agentzero.scrape.browser_linkedin import (
        build_linkedin_search_url,
        page_has_job_results,
        page_needs_human,
        parse_linkedin_search_html,
    )

    return (
        "LinkedIn",
        page_needs_human,
        page_has_job_results,
        build_linkedin_search_url,
        lambda html, source="linkedin": parse_linkedin_search_html(html, source=source),
        ('button:has-text("Accept")',),
    )


def _glassdoor_cfg() -> SiteConfig:
    from agentzero.scrape.browser_glassdoor import (
        build_glassdoor_search_url,
        page_has_job_results,
        page_needs_human,
        parse_glassdoor_search_html,
    )

    return (
        "Glassdoor",
        page_needs_human,
        page_has_job_results,
        build_glassdoor_search_url,
        lambda html, source="glassdoor": parse_glassdoor_search_html(html, source=source),
        ('button:has-text("Accept All")', 'button:has-text("Accept")'),
    )


SITE_CONFIGS: dict[str, SiteConfig] = {
    "indeed": _indeed_cfg(),
    "linkedin": _linkedin_cfg(),
    "glassdoor": _glassdoor_cfg(),
}


class BrowserJobBoardSource(JobSource):
    """One Playwright search per run for a single job board."""

    def __init__(
        self,
        settings: Settings,
        *,
        site: str,
        input_fn: Callable[[str], str] | None = None,
    ) -> None:
        key = site.lower()
        if key not in SITE_CONFIGS:
            raise ValueError(f"Unsupported browser site: {site}")
        self._settings = settings
        self._site_key = key
        self._cfg = SITE_CONFIGS[key]
        self._input_fn = input_fn

    @property
    def name(self) -> str:
        return f"{self._site_key}_browser"

    def fetch(self, *, progress: object | None = None) -> Sequence[RawRecord]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            return self.fetch_with_playwright(pw, progress=progress)

    def fetch_with_playwright(
        self,
        playwright: object,
        *,
        progress: object | None = None,
    ) -> Sequence[RawRecord]:
        return self._fetch_board(playwright, stop_playwright=False)

    def _fetch_board(self, playwright: object, *, stop_playwright: bool) -> Sequence[RawRecord]:
        display, needs_human, has_results, build_url, parse_html, consent = self._cfg
        term, parsed = primary_scrape_query(self._settings)
        url = build_url(term=term, parsed=parsed)

        read = self._input_fn or _default_input
        pause = (
            not self._settings.scrape_browser_headless
            and self._settings.scrape_browser_pause_for_captcha
        )

        print(
            f"[{display}] Opening browser — {term!r} @ {parsed.jobspy_location}"
            f"{' (remote)' if parsed.is_remote else ''}…",
            flush=True,
        )

        context = browser = None
        try:
            playwright, context, page, browser = launch_browser_page(
                self._settings,
                site=self._site_key,
                playwright=playwright,
            )
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            if not validate_browser_page_url(page):
                return []

            if self._settings.scrape_session_preflight:
                from agentzero.scrape.browser_session import (
                    SessionState,
                    classify_session,
                    session_status_message,
                )

                pre_html = page.content()
                pre_state = classify_session(self._site_key, pre_html, page.url)
                if pre_state is SessionState.LOGIN_REQUIRED:
                    print(session_status_message(self._site_key, pre_state), file=sys.stderr)
                    log.warning("%s browser: preflight login required — skipping fetch", display)
                    return []

            if self._site_key == "indeed":
                from agentzero.scrape.browser_indeed import _dismiss_indeed_consent

                _dismiss_indeed_consent(page)
            else:
                click_consent_buttons(page, consent)

            html = wait_for_html(page, predicate=has_results, timeout_ms=30_000)

            def _reload_search(p: object) -> None:
                p.goto(url, wait_until="domcontentloaded", timeout=60_000)  # type: ignore[union-attr]
                if not validate_browser_page_url(p):  # type: ignore[arg-type]
                    return
                if self._site_key == "indeed":
                    from agentzero.scrape.browser_indeed import _dismiss_indeed_consent

                    _dismiss_indeed_consent(p)
                else:
                    click_consent_buttons(p, consent)

            maybe_wait_for_human(
                page,
                site=display,
                html=html,
                needs_human=needs_human,
                input_fn=read,
                pause_enabled=pause,
                has_results=has_results,
                after_prompt=_reload_search if pause else None,
            )

            if pause and not has_results(page.content()):  # type: ignore[union-attr]
                try:
                    current_url = page.url  # type: ignore[union-attr]
                    if needs_human(page.content(), current_url):  # type: ignore[union-attr]
                        log.info("%s browser: still blocked — reloading search once more", display)
                        _reload_search(page)
                        wait_for_html(page, predicate=has_results, timeout_ms=20_000)
                except Exception:
                    pass

            html = page.content()  # type: ignore[union-attr]
            records = parse_html(html, source=self._site_key)
            if not records:
                html = wait_for_html(page, predicate=has_results, timeout_ms=15_000)
                records = parse_html(html, source=self._site_key)

            if parsed.is_remote:
                from agentzero.scrape.remote_policy import apply_remote_search_trust_to_record

                for record in records:
                    apply_remote_search_trust_to_record(record, remote_search=True)

            from agentzero.scrape.title_filter import title_matches_search

            before = len(records)
            records = [r for r in records if title_matches_search(str(r.get("title", "")), [term])]
            dropped = before - len(records)
            if dropped:
                log.info(
                    "%s browser: dropped %d off-topic title(s) for %r",
                    display,
                    dropped,
                    term,
                )

            log.info(
                "%s browser: %d rows for %r @ %r (remote=%s)",
                display,
                len(records),
                term,
                parsed.raw,
                parsed.is_remote,
            )
            return records[: self._settings.results_wanted]
        except Exception as exc:
            from agentzero.log_redaction import redact_secrets

            log.warning("%s browser fetch failed: %s", display, redact_secrets(str(exc)))
            return []
        finally:
            close_browser_session(
                playwright,
                context,
                self._settings,
                site=self._site_key,
                browser=browser,
                stop_playwright=stop_playwright,
            )


def _default_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""
