#!/usr/bin/env python3
"""Verify a job-board browser profile is ready to scrape.

Usage:

    python scripts/verify_browser_session.py --site glassdoor
    python scripts/verify_browser_session.py --site linkedin,indeed

Exit codes:
    0 — ready (listings or trusted session)
    1 — login required
    2 — blocked (CAPTCHA / Cloudflare)
    3 — error / unknown
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify browser session for job-board scrape")
    parser.add_argument(
        "--site",
        default="glassdoor",
        help="Comma-separated sites: indeed, linkedin, glassdoor",
    )
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.scrape.browser_session import session_status_message
    from agentzero.scrape.session_probe import probe_browser_session

    settings = get_settings()
    sites = [s.strip().lower() for s in args.site.split(",") if s.strip()]
    worst = 0

    for site in sites:
        result = probe_browser_session(settings, site)
        if result.error:
            print(f"ERROR [{site}]: {result.error}", file=sys.stderr)
            worst = max(worst, 3)
            continue
        print(session_status_message(site, result.state))
        if result.listing_count:
            print(f"  listings visible: {result.listing_count}")
        print(f"  url: {result.url[:100]}")
        worst = max(worst, result.exit_code)

    return worst


if __name__ == "__main__":
    raise SystemExit(main())
