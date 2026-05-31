#!/usr/bin/env python3
"""Remove DB jobs that are no longer in the Google Sheet.

Usage:

    python scripts/prune_db_from_sheet.py --dry-run
    python scripts/prune_db_from_sheet.py --yes
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
        description="Delete SQLite jobs not present in the Google Sheet",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without changing the DB",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion of DB rows not in the sheet",
    )
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.google.sync import plan_prune_db_to_sheet, prune_db_to_sheet
    from agentzero.storage.db import Database

    settings = get_settings()
    if not settings.sheet_id:
        print("ERROR: AGENTZERO_SHEET_ID is not set.", file=sys.stderr)
        return 1

    db_path = args.db or settings.db_path
    db = Database(db_path)

    try:
        plan = plan_prune_db_to_sheet(db=db, settings=settings)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Sheet: {plan.spreadsheet_title!r}")
    print(f"  Rows in sheet: {plan.sheet_job_count}")
    print(f"  Jobs in DB:    {plan.db_job_count}")
    print(f"  To delete:     {len(plan.to_delete)}")
    if plan.missing_in_db:
        print(f"  In sheet only (not in DB): {len(plan.missing_in_db)}")

    if plan.to_delete:
        print("\nWould remove from DB:")
        for job_id in plan.to_delete:
            job = db.get_job(job_id)
            label = f"{job.title} @ {job.company}" if job else job_id
            print(f"  - {label}")

    if args.dry_run or not plan.to_delete:
        if args.dry_run:
            print("\nDry run — no changes made.")
        return 0

    if not args.yes:
        print(
            "\nERROR: pass --yes to delete these rows, or --dry-run to preview.",
            file=sys.stderr,
        )
        return 1

    kept, deleted, title = prune_db_to_sheet(db=db, settings=settings)
    print(f"\nDeleted {deleted} job(s) from DB ({kept} kept matching {title!r}).")
    print(f"DB now has {db.count_jobs()} row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
