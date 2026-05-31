#!/usr/bin/env python3
"""Sync jobs from SQLite to the configured Google Sheet.

Usage (from repo root, venv active):

    pip install -e ".[google]"
    python scripts/google_auth.py              # one-time OAuth
    python scripts/sync_sheets.py --dry-run    # preview row count
    python scripts/sync_sheets.py --yes        # import sheet dates/status, then rewrite rows
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync AgentZero SQLite jobs to Google Sheets")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print job count without writing to the Sheet",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm worksheet rewrite (imports date_applied/status from sheet first)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: AGENTZERO_DB_PATH / data/agentzero.db)",
    )
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.google.auth import SHEETS_SCOPES
    from agentzero.google.sync import sync_jobs_to_sheet
    from agentzero.rank.export_filter import filter_jobs_for_export
    from agentzero.storage.db import Database

    get_settings.cache_clear()
    settings = get_settings()
    db_path = args.db or settings.db_path

    if not db_path.is_file():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        print("Run a scrape first: python scripts/run_scrape.py", file=sys.stderr)
        return 1

    if not settings.sheet_id:
        print(
            "ERROR: AGENTZERO_SHEET_ID is not set in .env.\n"
            "Copy the spreadsheet ID from your Google Sheet URL.",
            file=sys.stderr,
        )
        return 1

    db = Database(db_path)
    jobs = db.list_jobs()
    export_jobs, below_floor = filter_jobs_for_export(jobs, settings.min_match_score)
    print(f"Database: {db_path.resolve()}")
    print(f"Jobs:     {len(jobs)}")
    if below_floor and settings.min_match_score:
        print(
            f"Export:   {len(export_jobs)} "
            f"(min match_score {settings.min_match_score:g}; "
            f"{len(below_floor)} below floor, applied jobs always kept)"
        )
    print(f"Sheet ID: {settings.sheet_id}")

    if args.dry_run:
        print("Dry run — no changes written to Google Sheets.")
        return 0

    if not args.yes:
        print(
            "\nERROR: sync rewrites the worksheet (user-edited columns are imported into SQLite first).",
            file=sys.stderr,
        )
        print(
            "Confirm AGENTZERO_SHEET_ID is correct, then re-run with --yes.",
            file=sys.stderr,
        )
        return 1

    if not settings.google_token_path.is_file():
        print(
            f"ERROR: {settings.google_token_path} not found.\n"
            "Run: python scripts/google_auth.py",
            file=sys.stderr,
        )
        return 1

    try:
        result = sync_jobs_to_sheet(
            db=db,
            settings=settings,
            scopes=SHEETS_SCOPES,
        )
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Sheets sync failed: {exc}", file=sys.stderr)
        return 1

    if result.imported:
        parts = [f"Imported tracker fields for {result.imported} job(s) from the sheet into SQLite."]
        if result.created:
            parts.append(f"Created {result.created} restored job(s).")
        print(" ".join(parts))
    if result.skipped_unknown_job_id:
        print(
            f"Note: {result.skipped_unknown_job_id} sheet row(s) had job_id not in DB (skipped)."
        )
    print(f"OK — synced {result.row_count} job(s) to {result.spreadsheet_title!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
