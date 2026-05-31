#!/usr/bin/env python3
"""Clear scraped jobs from SQLite (and optionally Google Sheets).

Usage:

    python scripts/clear_jobs.py
    python scripts/clear_jobs.py --sync-sheet   # also wipe the Sheet (header only)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear AgentZero job database")
    parser.add_argument(
        "--sync-sheet",
        action="store_true",
        help="After clearing DB, push empty sheet (header row only)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: AGENTZERO_DB_PATH)",
    )
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.storage.db import Database

    settings = get_settings()
    db_path = args.db or settings.db_path
    db = Database(db_path)

    jobs_deleted, quarantine_deleted = db.clear_all()
    print(f"Cleared {jobs_deleted} job(s) and {quarantine_deleted} quarantine row(s) from {db_path}")

    if args.sync_sheet:
        if not settings.sheet_id:
            print("WARNING: AGENTZERO_SHEET_ID not set — skipping Sheet sync.", file=sys.stderr)
            return 0
        from agentzero.google.sync import sync_jobs_to_sheet

        try:
            result = sync_jobs_to_sheet(db=db, settings=settings)
        except Exception as exc:
            print(f"ERROR: Sheet sync failed: {exc}", file=sys.stderr)
            return 1
        if result.imported:
            print(f"Imported user fields for {result.imported} job(s) from the sheet.")
        print(f"Sheet {result.spreadsheet_title!r} updated ({result.row_count} data rows).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
