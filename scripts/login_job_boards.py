#!/usr/bin/env python3
"""Log in to job boards once; cookies persist for scrape runs.

Usage (from repo root, venv active):

    python scripts/login_job_boards.py
    python scripts/login_job_boards.py --site indeed
    python scripts/login_job_boards.py --site indeed,linkedin,glassdoor

LinkedIn uses a Playwright profile under ``data/browser_profiles/linkedin``.
Indeed and Glassdoor use CDP (your real Chrome) when ``AGENTZERO_SCRAPE_CDP_URL`` is set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log in to job boards via Playwright (persistent cookies)"
    )
    parser.add_argument(
        "--site",
        default="indeed,linkedin,glassdoor",
        help="Comma-separated boards (default: all core browser sites)",
    )
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.scrape.browser_auth import LOGIN_URLS, login_sites
    from agentzero.scrape.browser_common import cdp_setup_hint

    settings = get_settings()
    sites = [s.strip().lower() for s in args.site.split(",") if s.strip()]
    unknown = [s for s in sites if s not in LOGIN_URLS]
    if unknown:
        print(f"ERROR: unknown site(s): {unknown}", file=sys.stderr)
        print(f"Valid: {', '.join(LOGIN_URLS)}", file=sys.stderr)
        return 1

    cdp_sites = [s for s in sites if settings.use_cdp_for_site(s)]
    playwright_sites = [s for s in sites if not settings.use_cdp_for_site(s)]

    if cdp_sites and settings.scrape_cdp_url:
        from agentzero.scrape.browser_common import ensure_cdp_for_sites

        try:
            ensure_cdp_for_sites(settings)
        except RuntimeError as exc:
            print(f"ERROR: {exc}\n", file=sys.stderr)
            print(cdp_setup_hint(settings), file=sys.stderr)
            return 1
    elif cdp_sites and not settings.scrape_cdp_url:
        print("ERROR: Indeed/Glassdoor require CDP (real Chrome profile).\n", file=sys.stderr)
        print(cdp_setup_hint(settings), file=sys.stderr)
        return 1

    if cdp_sites:
        print(
            f"CDP Chrome ({settings.scrape_cdp_url}): {', '.join(cdp_sites)} — "
            "use your normal Chrome window (MFA OK)."
        )
    if playwright_sites:
        print(
            f"Playwright profile: {', '.join(playwright_sites)} — "
            "a separate Chrome window opens per site."
        )
    print("Complete login + 2FA in each browser window.\n")

    results = login_sites(settings, sites)
    print("\nLogin summary:")
    for site, status in results.items():
        if status == "ready":
            label = "ready"
        elif status == "enter_override":
            label = "saved (Enter override — verify with verify_browser_session)"
        elif status == "timeout":
            label = "timeout — retry login"
        else:
            label = f"{status} — retry login"
        print(f"  {site}: {label}")
    print("\nNext: python scripts/verify_browser_session.py --site " + ",".join(sites))
    print("Then: python scripts/run_scrape.py --limit 25")
    ok_statuses = {"ready", "enter_override"}
    return 0 if all(s in ok_statuses for s in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
