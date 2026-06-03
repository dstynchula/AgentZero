"""Safe relative redirects from legacy /config URLs to /scraper."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request

_ALLOWED_CONFIG_PATHS = frozenset(
    {
        "sources",
        "resume/load",
        "search-titles",
        "search-titles/add",
        "search-titles/remove",
        "cdp/connect",
        "scrape",
    }
)

_ALLOWED_FLASH_QUERY_KEYS = frozenset(
    {
        "saved",
        "titles_saved",
        "title_added",
        "title_removed",
        "cdp_ok",
        "cdp_fail",
        "msg",
        "scrape_started",
        "scrape_busy",
        "resume_loading",
        "resume_busy",
    }
)


def safe_legacy_scraper_path(path: str) -> str:
    """Return allowlisted subpath under /scraper, or empty for /scraper root."""
    normalized = (path or "").strip().strip("/")
    if not normalized or normalized not in _ALLOWED_CONFIG_PATHS:
        return ""
    if "://" in normalized or ".." in normalized or "\\" in normalized:
        return ""
    return normalized


def safe_flash_query(request: Request) -> str:
    """Rebuild query string from allowlisted flash/status keys only."""
    items = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key in _ALLOWED_FLASH_QUERY_KEYS
    ]
    if not items:
        return ""
    return "?" + urlencode(items)


def legacy_scraper_redirect_base(path: str = "") -> str:
    """Return a fixed relative /scraper URL for a legacy /config path segment.

    Uses only literal targets so redirect URLs are not built from user input
    (CodeQL py/unsafe-redirect).
    """
    match safe_legacy_scraper_path(path):
        case "sources":
            return "/scraper/sources"
        case "resume/load":
            return "/scraper/resume/load"
        case "search-titles":
            return "/scraper/search-titles"
        case "search-titles/add":
            return "/scraper/search-titles/add"
        case "search-titles/remove":
            return "/scraper/search-titles/remove"
        case "cdp/connect":
            return "/scraper/cdp/connect"
        case "scrape":
            return "/scraper/scrape"
        case _:
            return "/scraper"


def legacy_scraper_redirect_url(request: Request, path: str = "") -> str:
    """Relative redirect target for legacy /config bookmarks."""
    return legacy_scraper_redirect_base(path) + safe_flash_query(request)


def legacy_api_scraper_redirect_url(request: Request) -> str:
    return f"/api/scraper{safe_flash_query(request)}"
