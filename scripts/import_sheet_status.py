#!/usr/bin/env python3
"""Import application tracking from Google Sheet into SQLite.

Restores ``date_applied``, ``status``, and ``notes`` — and recreates jobs you
re-added to the sheet after a purge (matched by URL or company+title).

Usage:

    python scripts/import_sheet_status.py
    python scripts/import_sheet_status.py --dry-run
    python scripts/import_sheet_status.py --sync
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
        description="Import application tracking from Google Sheet into SQLite"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Import then push DB back to sheet (sync_sheets --yes)",
    )
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    from agentzero.apply.tracking import (
        import_tracker_rows,
        list_applied_jobs,
        tracker_rows_with_applications,
    )
    from agentzero.config import get_settings
    from agentzero.google.auth import SHEETS_SCOPES
    from agentzero.google.sync import _sheets_sync, sync_jobs_to_sheet
    from agentzero.storage.db import Database

    settings = get_settings()
    db_path = args.db or settings.db_path
    if not db_path.is_file():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1
    if not settings.sheet_id:
        print("ERROR: AGENTZERO_SHEET_ID is not set.", file=sys.stderr)
        return 1
    if not settings.google_token_path.is_file():
        print(f"ERROR: {settings.google_token_path} not found. Run google_auth.py.", file=sys.stderr)
        return 1

    sync, spreadsheet = _sheets_sync(settings, SHEETS_SCOPES)
    rows = sync.read_tracker_rows()
    applied_rows = tracker_rows_with_applications(rows)

    db = Database(db_path)
    try:
        preview = import_tracker_rows(db, rows, dry_run=True)

        print(f"Sheet: {spreadsheet.title!r}")
        print(f"Rows read: {len(rows)}")
        print(f"Rows with application data: {len(applied_rows)}")
        print(f"Would update existing jobs: {preview.updated}")
        print(f"Would create restored jobs: {preview.created}")
        print(f"Applied jobs currently in DB: {len(list_applied_jobs(db))}")

        if args.dry_run:
            return 0

        result = import_tracker_rows(db, rows)
        print(f"\nUpdated {result.updated} job(s), created {result.created} restored job(s).")
        print(f"Applied jobs in DB now: {len(list_applied_jobs(db))}")

        if args.sync:
            sheet_result = sync_jobs_to_sheet(db=db, settings=settings, scopes=SHEETS_SCOPES)
            print(f"Synced {sheet_result.row_count} job(s) to {sheet_result.spreadsheet_title!r}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
