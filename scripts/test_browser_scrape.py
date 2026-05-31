#!/usr/bin/env python3
"""Quick live browser scrape test (single query, one board).

  python scripts/test_browser_scrape.py --site indeed --remote
  python scripts/test_browser_scrape.py --site linkedin --term "Security Engineer" --remote
  python scripts/test_browser_scrape.py --site glassdoor --remote --headless
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentzero.config import Settings
from agentzero.ingest.search_profile import ResumeSearchProfile, apply_search_profile
from agentzero.ingest.work_mode import apply_work_mode_selection, selection_from_work_mode
from agentzero.scrape.browser_board import BrowserJobBoardSource


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["indeed", "linkedin", "glassdoor"], default="indeed")
    parser.add_argument("--term", default="Staff Security Engineer")
    parser.add_argument("--remote", action="store_true", help="Remote USA search")
    parser.add_argument("--office", default="Los Angeles, CA", help="Office location if not --remote")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    base = Settings(_env_file=None, scrape_browser_headless=args.headless, results_wanted=args.limit)
    profile = ResumeSearchProfile(
        search_terms=[args.term],
        locations=["remote - usa"] if args.remote else [args.office],
        remote_preferred=args.remote,
        source_resume_path="scripts/test_browser_scrape.py",
        source_fingerprint="test",
        updated_at="2026-01-01T00:00:00Z",
    )
    if args.remote:
        sel = selection_from_work_mode("remote")
    else:
        sel = selection_from_work_mode("in_office", office_locations=[args.office])
    profile = apply_work_mode_selection(profile, sel)
    settings = apply_search_profile(base, profile)

    print(f"Testing {args.site} browser: {settings.search_terms[0]!r} @ {settings.locations}")
    source = BrowserJobBoardSource(settings, site=args.site)
    records = source.fetch()
    print(f"\nGot {len(records)} jobs")
    for row in records[:5]:
        print(f"  - {row.get('title')} @ {row.get('company')} ({row.get('url', '')[:60]}...)")
    if len(records) > 5:
        print(f"  ... and {len(records) - 5} more")
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
