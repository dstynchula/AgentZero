#!/usr/bin/env python3
"""Secondary enrichment: job detail pages, Glassdoor, and web search.

List scrapes (especially LinkedIn) often omit salary, company size, and ratings.
This script fetches each job's posting URL (HTTP, then browser if needed), parses
description/comp hints, looks up Glassdoor, and runs DuckDuckGo searches per
company for size, Glassdoor snippets, and careers-page URLs (when the role appears
on the company site).

Usage:

    python scripts/enrich_jobs.py
    python scripts/enrich_jobs.py --limit 10
    python scripts/enrich_jobs.py --no-browser    # HTTP only (faster, less complete)
    python scripts/enrich_jobs.py --workers 8     # parallel HTTP/Glassdoor phase
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep-enrich jobs in SQLite")
    parser.add_argument("--limit", type=int, default=None, help="Max jobs to process")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip Playwright fallback (HTTP detail fetch only)",
    )
    parser.add_argument(
        "--no-glassdoor",
        action="store_true",
        help="Skip Glassdoor company rating lookup",
    )
    parser.add_argument(
        "--no-web-search",
        action="store_true",
        help="Skip DuckDuckGo web search for size, Glassdoor, careers pages",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel workers for HTTP/Glassdoor (default: AGENTZERO_ENRICH_MAX_CONCURRENCY)",
    )
    parser.add_argument("--force", action="store_true", help="Re-enrich all jobs, not only gaps")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.enrich.batch import run_enrich_batch
    from agentzero.enrich.gaps import needs_enrichment_pass
    from agentzero.storage.db import Database

    settings = get_settings()
    db_path = args.db or settings.db_path
    if not db_path.is_file():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1

    db = Database(db_path)
    jobs = db.list_jobs()
    if args.force:
        targets = jobs
    else:
        targets = [j for j in jobs if needs_enrichment_pass(j)]

    if args.limit is not None:
        targets = targets[: args.limit]

    if not targets:
        print("No jobs need enrichment (use --force to re-run all).")
        return 0

    workers = args.workers if args.workers is not None else settings.enrich_max_concurrency
    workers = max(1, workers)
    fetch_detail = settings.enrich_fetch_details
    allow_browser = fetch_detail and not args.no_browser
    glassdoor = settings.enrich_glassdoor_lookup and not args.no_glassdoor
    web_search = settings.enrich_web_search and not args.no_web_search

    print(f"Deep-enriching {len(targets)} job(s)…\n", flush=True)

    result = run_enrich_batch(
        db,
        [j.job_id for j in targets],
        settings=settings,
        max_workers=workers,
        fetch_detail=fetch_detail,
        glassdoor_lookup=glassdoor,
        web_search=web_search,
        allow_browser=allow_browser,
        browser_delay_seconds=settings.enrich_delay_seconds,
    )

    print(
        f"\nEnrichment pass done ({result.improved}/{result.total} improved"
        f"{f', {result.failed} failed' if result.failed else ''}).",
        flush=True,
    )

    if result.failed:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
