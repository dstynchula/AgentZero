#!/usr/bin/env python3
"""Import cookies from Chrome/Edge into AgentZero Playwright storage state.

Supports Cookie-Editor JSON export or Playwright storage_state format.

Usage:

    python scripts/import_browser_cookies.py --site glassdoor --from cookies.json
    python scripts/import_browser_cookies.py --site linkedin --from export.json --apply

``--apply`` opens the site profile briefly so cookies persist in the Chromium profile dir.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Import browser cookies for Playwright scrape")
    parser.add_argument(
        "--site",
        required=True,
        choices=["indeed", "linkedin", "glassdoor"],
        help="Job board profile to target",
    )
    parser.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        help="Cookie-Editor JSON or Playwright storage_state file",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Open browser profile so cookies merge into persistent storage",
    )
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.scrape.browser_session import import_cookies_file, storage_state_path

    settings = get_settings()
    source = args.source
    if not source.is_file():
        print(f"ERROR: file not found: {source}", file=sys.stderr)
        return 1

    dest = storage_state_path(settings, args.site)
    try:
        count = import_cookies_file(source, dest)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"OK — wrote {count} cookie(s) to {dest.resolve()}")

    if not args.apply:
        print("Next scrape run will load these cookies automatically.")
        return 0

    from agentzero.scrape.browser_common import close_browser_session, launch_browser_page

    print(f"Opening {args.site} profile to persist cookies…")
    playwright = context = None
    try:
        playwright, context, page = launch_browser_page(settings, site=args.site)
        page.goto("about:blank")
        print("Cookies loaded. Press Enter to save profile and close.")
        input()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        close_browser_session(playwright, context, settings, site=args.site)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
