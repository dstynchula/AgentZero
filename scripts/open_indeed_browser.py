#!/usr/bin/env python3
"""Open Indeed in a visible Chromium window to pass CAPTCHA/consent once.

Cookies are saved to ``data/indeed_browser_profile`` and reused by scrape runs.

Usage:

    python scripts/open_indeed_browser.py
    python scripts/open_indeed_browser.py --query "Staff Security Engineer" --location "Remote"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote_plus

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

INDEED_JOBS = "https://www.indeed.com/jobs"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open Indeed in Chromium for manual CAPTCHA/consent (persistent profile)"
    )
    parser.add_argument("--query", default="", help="Optional job title search")
    parser.add_argument("--location", default="", help="Optional location")
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.scrape.browser_indeed import prompt_for_browser_verification
    from agentzero.scrape.resilience import DEFAULT_USER_AGENT

    settings = get_settings()
    profile_dir = settings.scrape_browser_profile_dir
    profile_dir.mkdir(parents=True, exist_ok=True)

    if args.query or args.location:
        url = (
            f"{INDEED_JOBS}?q={quote_plus(args.query)}&l={quote_plus(args.location)}"
        )
    else:
        url = INDEED_JOBS

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "ERROR: Playwright not installed.\n"
            "Run: pip install -e '.[scrape]' && python -m playwright install chromium",
            file=sys.stderr,
        )
        return 1

    print(f"Profile: {profile_dir.resolve()}")
    print(f"Opening: {url}")
    print("A Chromium window will stay open until you press Enter here.")

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            user_agent=settings.scrape_user_agent or DEFAULT_USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        prompt_for_browser_verification(
            reason="Pass Indeed CAPTCHA/consent now. Your session will be saved for future scrapes.",
        )

        print("Closing browser — profile saved.")
        context.close()

    print("Done. Run: python scripts/run_scrape.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
