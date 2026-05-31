"""Manual login helpers for Playwright job-board profiles."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from agentzero.scrape.browser_common import (
    _consume_enter,
    _enter_pressed,
    close_browser_session,
    launch_browser_page,
)

if TYPE_CHECKING:
    from agentzero.config import Settings

log = logging.getLogger(__name__)

INDEED_LOGIN_URL = (
    "https://secure.indeed.com/account/login"
    "?hl=en&continue=https%3A%2F%2Fwww.indeed.com"
)

LOGIN_URLS: dict[str, tuple[str, str]] = {
    "indeed": ("Indeed", INDEED_LOGIN_URL),
    "linkedin": ("LinkedIn", "https://www.linkedin.com/login"),
    "glassdoor": ("Glassdoor", "https://www.glassdoor.com/profile/login_input.htm"),
}


def _still_on_login_wall(site: str, html: str, url: str) -> bool:
    """Return True while the browser is still on a login/sign-in wall."""
    key = site.lower()
    if key == "indeed":
        from agentzero.scrape.browser_indeed import page_needs_human, page_needs_login

        return page_needs_login(html, url) or page_needs_human(html, url)
    if key == "linkedin":
        from agentzero.scrape.browser_linkedin import page_needs_login

        return page_needs_login(html, url)
    if key == "glassdoor":
        from agentzero.scrape.browser_glassdoor import page_needs_login

        return page_needs_login(html, url)
    return False


def _page_content_transient_error(exc: Exception) -> bool:
    """True when page.content() failed because the tab is mid-navigation (not closed)."""
    msg = str(exc).lower()
    return "navigating" in msg or "changing the content" in msg


def wait_for_login(
    page: object,
    *,
    site: str,
    display: str,
    max_wait_sec: float = 600.0,
) -> str:
    """Poll until login completes. Returns: ready | enter_override | timeout | closed."""
    deadline = time.time() + max_wait_sec
    announced = False

    while time.time() < deadline:
        try:
            html = page.content()  # type: ignore[union-attr]
            url = page.url  # type: ignore[union-attr]
        except Exception as exc:
            if _page_content_transient_error(exc):
                try:
                    page.wait_for_timeout(750)  # type: ignore[union-attr]
                except Exception:
                    return "closed"
                continue
            log.warning("%s: browser closed during login wait (%s)", display, exc)
            return "closed"

        if not _still_on_login_wall(site, html, url):
            log.info("%s: login session looks ready", display)
            return "ready"

        if not announced:
            print(
                f"\n{display}: sign in in the Chromium window "
                f"(2FA, Google SSO, etc.).\n"
                "We will continue automatically when the login wall is gone, "
                "or press Enter here to save cookies and continue anyway.\n",
                flush=True,
            )
            announced = True

        if _enter_pressed():
            _consume_enter()
            log.info("%s: enter_override — saving profile without confirmed login", display)
            return "enter_override"

        try:
            page.wait_for_timeout(1500)  # type: ignore[union-attr]
        except Exception:
            return "closed"

    print(f"{display}: login wait timed out — profile saved; try again before scraping.")
    return "timeout"


def login_site(settings: Settings, site: str) -> str:
    """Open login page in persistent profile; wait for user to authenticate."""
    key = site.strip().lower()
    if key not in LOGIN_URLS:
        raise ValueError(f"Unknown site {site!r}; choose from: {', '.join(LOGIN_URLS)}")

    display, login_url = LOGIN_URLS[key]
    playwright = context = None
    try:
        playwright, context, page = launch_browser_page(settings, site=key)
        page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)  # type: ignore[union-attr]
        return wait_for_login(page, site=key, display=display)
    finally:
        close_browser_session(playwright, context, settings, site=key)


def login_sites(settings: Settings, sites: list[str]) -> dict[str, str]:
    """Log in to each site sequentially (separate browser profiles)."""
    results: dict[str, str] = {}
    for site in sites:
        key = site.strip().lower()
        if not key:
            continue
        print(f"\n{'=' * 60}\nOpening {key} login…\n{'=' * 60}", flush=True)
        results[key] = login_site(settings, key)
    return results
