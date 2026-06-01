"""Browser session helpers: storage state paths, cookie import, CDP attach."""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentzero.config import Settings

log = logging.getLogger(__name__)

SUPPORTED_SITES = frozenset({"indeed", "linkedin", "glassdoor"})


class SessionState(StrEnum):
    READY = "ready"
    LOGIN_REQUIRED = "login_required"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


SESSION_EXIT_CODES: dict[SessionState, int] = {
    SessionState.READY: 0,
    SessionState.LOGIN_REQUIRED: 1,
    SessionState.BLOCKED: 2,
    SessionState.UNKNOWN: 3,
}


def _site_page_helpers(site: str) -> tuple:
    key = site.strip().lower()
    if key == "indeed":
        from agentzero.scrape.browser_indeed import (
            page_has_job_results,
            page_needs_human,
            page_needs_login,
            page_session_ready,
        )

        return page_session_ready, page_needs_login, page_needs_human, page_has_job_results
    if key == "linkedin":
        from agentzero.scrape.browser_linkedin import (
            page_needs_human,
            page_needs_login,
            page_session_ready,
        )

        return page_session_ready, page_needs_login, page_needs_human, page_session_ready
    if key == "glassdoor":
        from agentzero.scrape.browser_glassdoor import (
            page_needs_human,
            page_needs_login,
            page_session_ready,
        )

        return page_session_ready, page_needs_login, page_needs_human, page_session_ready
    raise ValueError(f"Unsupported site: {site}")


def classify_session(site: str, html: str, url: str = "") -> SessionState:
    """Classify browser page state for scrape/login workflows."""
    ready_fn, login_fn, block_fn, _ = _site_page_helpers(site)
    if ready_fn(html, url):
        return SessionState.READY
    if login_fn(html, url):
        return SessionState.LOGIN_REQUIRED
    if block_fn(html, url):
        return SessionState.BLOCKED
    return SessionState.UNKNOWN


def session_status_message(site: str, state: SessionState) -> str:
    if state is SessionState.READY:
        return f"{site}: session ready for scraping."
    if state is SessionState.LOGIN_REQUIRED:
        return f"{site}: login required — run: python scripts/login_job_boards.py --site {site}"
    if state is SessionState.BLOCKED:
        return (
            f"{site}: blocked (CAPTCHA/Cloudflare) — solve in browser or import cookies "
            f"(see docs/SCRAPING.md)."
        )
    return f"{site}: session state unknown — try login_job_boards or verify again."


def storage_state_path(settings: Settings, site: str) -> Path:
    """Per-site Playwright storage state JSON (cookies + origins)."""
    key = site.strip().lower()
    return settings.scrape_storage_state_dir / f"{key}.json"


def normalize_cookies(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Cookie-Editor / browser export rows to Playwright cookie dicts."""
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        domain = item.get("domain")
        if not name or value is None or not domain:
            continue
        cookie: dict[str, Any] = {
            "name": str(name),
            "value": str(value),
            "domain": str(domain),
            "path": str(item.get("path") or "/"),
        }
        if "expires" in item and item["expires"] is not None:
            cookie["expires"] = float(item["expires"])
        elif "expirationDate" in item and item["expirationDate"] is not None:
            cookie["expires"] = float(item["expirationDate"])
        if item.get("httpOnly") is not None:
            cookie["httpOnly"] = bool(item["httpOnly"])
        if item.get("secure") is not None:
            cookie["secure"] = bool(item["secure"])
        same_site = item.get("sameSite")
        if same_site is not None:
            if isinstance(same_site, str):
                ss = same_site.capitalize()
                if ss in ("Strict", "Lax", "None"):
                    cookie["sameSite"] = ss
            elif same_site is True:
                cookie["sameSite"] = "Strict"
        out.append(cookie)
    return out


def parse_cookie_import(payload: object) -> dict[str, Any]:
    """Accept Playwright storage_state or a bare cookie array."""
    if isinstance(payload, dict) and "cookies" in payload:
        cookies = normalize_cookies(list(payload.get("cookies") or []))
        origins = list(payload.get("origins") or [])
        return {"cookies": cookies, "origins": origins}
    if isinstance(payload, list):
        return {"cookies": normalize_cookies(payload), "origins": []}
    raise ValueError(
        "Expected Playwright storage_state object or a JSON array of cookies "
        "(Cookie-Editor export)."
    )


def load_storage_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_cookie_import(data)


def save_storage_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def import_cookies_file(source: Path, dest: Path) -> int:
    """Read cookie export from *source*, write Playwright storage_state to *dest*."""
    payload = json.loads(source.read_text(encoding="utf-8"))
    state = parse_cookie_import(payload)
    save_storage_state(dest, state)
    return len(state["cookies"])


def apply_storage_state(context: Any, state: dict[str, Any]) -> None:
    """Inject cookies from storage state into an open browser context."""
    cookies = state.get("cookies") or []
    if cookies:
        context.add_cookies(cookies)
        log.info("Applied %d cookie(s) from storage state", len(cookies))
