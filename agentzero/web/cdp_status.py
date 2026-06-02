"""CDP connection summary for the web config page."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agentzero.config import Settings
from agentzero.scrape.browser_common import (
    cdp_endpoint_reachable,
    cdp_port,
    cdp_setup_hint,
    ensure_cdp_ready,
)
from agentzero.scrape.cdp_launch import build_launch_commands
from agentzero.web.operator_config import OperatorScrapeConfig, effective_scrape_lists

_SITE_LABELS = {
    "indeed": "Indeed",
    "linkedin": "LinkedIn",
    "glassdoor": "Glassdoor",
    "google": "Google Jobs",
    "zip_recruiter": "ZipRecruiter",
}


def _label(site: str) -> str:
    return _SITE_LABELS.get(site, site.replace("_", " ").title())


def _launch_port(settings: Settings) -> int:
    if settings.scrape_cdp_url:
        return cdp_port(settings.scrape_cdp_url)
    return 9222


def enabled_cdp_browser_sites(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    browser_on, _ = effective_scrape_lists(settings, operator)
    if not settings.scrape_cdp_url:
        return []
    return [site for site in browser_on if settings.use_cdp_for_site(site)]


def build_host_instructions(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> str:
    """Source-aware env and board notes (launch commands are separate in the UI)."""
    browser_on, jobspy_on = effective_scrape_lists(settings, operator)
    lines: list[str] = []

    if not browser_on and not jobspy_on:
        return "Enable at least one scrape source above."

    if jobspy_on:
        names = ", ".join(_label(s) for s in jobspy_on)
        lines.append(f"JobSpy (HTTP, no browser): {names}.")

    cdp_sites = enabled_cdp_browser_sites(settings, operator)
    playwright_browser = [s for s in browser_on if s not in cdp_sites]

    if cdp_sites:
        names = ", ".join(_label(s) for s in cdp_sites)
        lines.append(f"Log into these boards in the CDP Chrome window: {names}.")
        port = _launch_port(settings)
        if settings.scrape_cdp_url:
            lines.append(f"AGENTZERO_SCRAPE_CDP_URL={settings.scrape_cdp_url}")
        else:
            lines.append(f"AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:{port}")
        lines.append(f"AGENTZERO_SCRAPE_CDP_SITES={','.join(cdp_sites)}")
        if settings.scrape_cdp_auto_launch:
            lines.append("Auto-launch is on when the endpoint is down (host only).")

    if playwright_browser:
        names = ", ".join(_label(s) for s in playwright_browser)
        if settings.scrape_cdp_url and cdp_sites:
            lines.append(f"Playwright profile (no CDP): {names}.")
        else:
            lines.append(f"Playwright browser: {names}.")

    if settings.cdp_allow_docker_host or _docker_host_allowed():
        lines.append(
            "Docker: AGENTZERO_SCRAPE_CDP_URL=http://host.docker.internal:9222 "
            "and AGENTZERO_CDP_ALLOW_DOCKER_HOST=true."
        )

    return "\n".join(lines)


def _docker_host_allowed() -> bool:
    import os

    raw = os.environ.get("AGENTZERO_CDP_ALLOW_DOCKER_HOST", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _running_in_container() -> bool:
    return Path("/.dockerenv").is_file()


def _cdp_uses_loopback_host(cdp_url: str) -> bool:
    host = (urlparse(cdp_url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def _docker_cdp_unreachable_message(url: str) -> str:
    port = cdp_port(url)
    return (
        f"CDP at {url} is not reachable from inside Docker. "
        "Launch Chrome on the host (Step 1), then use "
        f"AGENTZERO_SCRAPE_CDP_URL=http://host.docker.internal:{port} "
        "with AGENTZERO_CDP_ALLOW_DOCKER_HOST=true. "
        "docker compose up web sets both; rebuild/restart the web container after changing .env."
    )


def retry_cdp_connection(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> tuple[bool, str]:
    """Probe CDP; optionally auto-launch Chrome for enabled CDP boards."""
    url = settings.scrape_cdp_url
    if not url:
        return False, "Set AGENTZERO_SCRAPE_CDP_URL in .env, then use Connect."

    if cdp_endpoint_reachable(url):
        return True, f"Connected to Chrome at {url}."

    if _running_in_container():
        if _cdp_uses_loopback_host(url):
            return False, _docker_cdp_unreachable_message(url)
        return False, (
            f"CDP not reachable at {url}. Close any old Chrome debug session, then restart "
            "with scripts/launch_chrome_cdp.ps1 (or .py / .sh) — that starts Chrome on "
            "localhost and a host proxy so Docker can reach port "
            f"{cdp_port(url)}. Auto-launch does not run inside Docker."
        )

    cdp_sites = enabled_cdp_browser_sites(settings, operator)
    if not cdp_sites:
        return (
            False,
            "CDP URL is set but no enabled browser source uses CDP "
            f"(configured CDP sites: {', '.join(settings.scrape_cdp_sites) or 'all'}).",
        )

    if not settings.scrape_cdp_auto_launch:
        return False, cdp_setup_hint(settings)

    try:
        for site in cdp_sites:
            ensure_cdp_ready(settings, site=site)
            if cdp_endpoint_reachable(url):
                return True, f"Connected to Chrome at {url} (via {site})."
        return False, f"CDP still not reachable at {url}. {cdp_setup_hint(settings)}"
    except (OSError, RuntimeError, ValueError) as exc:
        return False, str(exc)


def cdp_status_payload(
    settings: Settings,
    operator: OperatorScrapeConfig | None = None,
) -> dict[str, Any]:
    url = settings.scrape_cdp_url
    cdp_sites = enabled_cdp_browser_sites(settings, operator)
    port = _launch_port(settings)
    launch_commands = build_launch_commands(port=port)
    host_instructions = build_host_instructions(settings, operator)
    base = {
        "auto_launch": settings.scrape_cdp_auto_launch,
        "cdp_sites": cdp_sites,
        "configured_cdp_sites": list(settings.scrape_cdp_sites),
        "host_instructions": host_instructions,
        "launch_commands": launch_commands,
        "launch_port": port,
        "needs_cdp": bool(cdp_sites),
    }
    if not url:
        return {
            **base,
            "configured": False,
            "reachable": False,
            "url": None,
            "hint": cdp_setup_hint(settings) if cdp_sites else None,
            "env_line": "AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:9222",
        }
    reachable = cdp_endpoint_reachable(url)
    return {
        **base,
        "configured": True,
        "reachable": reachable,
        "url": url,
        "hint": None if reachable else (cdp_setup_hint(settings) if cdp_sites else None),
        "env_line": f"AGENTZERO_SCRAPE_CDP_URL={url}",
    }
