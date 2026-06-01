#!/usr/bin/env python3
"""Open Glassdoor in a visible browser to pass CAPTCHA/login once.

Cookies are saved to ``data/browser_profiles/glassdoor`` and reused by scrape runs.

Usage:

    python scripts/open_glassdoor_browser.py
    python scripts/open_glassdoor_browser.py --query "Staff Security Engineer" --location "Remote"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_search_url(*, query: str, location: str, remote: bool) -> str:
    from agentzero.scrape.browser_glassdoor import build_glassdoor_search_url
    from agentzero.scrape.location import ParsedLocation

    parsed = ParsedLocation(
        raw=location,
        jobspy_location=location,
        browser_location=location,
        is_remote=remote,
        country_indeed="USA",
        omit_hours_old=False,
    )
    return build_glassdoor_search_url(term=query or "Software Engineer", parsed=parsed)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open Glassdoor in Chromium for manual CAPTCHA/login (persistent profile)"
    )
    parser.add_argument("--query", default="Staff Security Engineer", help="Job title search")
    parser.add_argument("--location", default="Remote", help="Location")
    parser.add_argument("--remote", action="store_true", help="Remote search (default when location is Remote)")
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.scrape.browser_common import close_browser_session, launch_browser_page
    from agentzero.scrape.browser_glassdoor import page_has_job_results, page_needs_human

    settings = get_settings()
    remote = args.remote or args.location.lower().startswith("remote")
    url = build_search_url(query=args.query, location=args.location, remote=remote)
    profile = settings.scrape_browser_profile_dir.parent / "browser_profiles" / "glassdoor"

    print(f"Profile: {profile.resolve()}")
    print(f"Opening: {url}")

    playwright = context = None
    try:
        playwright, context, page = launch_browser_page(settings, site="glassdoor")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        print(
            "\nComplete login/CAPTCHA in Chromium. Press Enter here when job listings appear "
            "or the block is gone."
        )
        input()
        html = page.content()
        if page_has_job_results(html):
            print("Listings detected — profile saved.")
        elif page_needs_human(html, page.url):
            print("WARNING: page still looks blocked; profile saved anyway.")
        else:
            print("Profile saved.")
    except ImportError:
        print(
            "ERROR: Playwright not installed.\n"
            "Run: pip install -e '.[scrape]' && python -m playwright install chromium",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        close_browser_session(playwright, context, settings, site="glassdoor")

    print("Done. Run: python scripts/verify_browser_session.py --site glassdoor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
