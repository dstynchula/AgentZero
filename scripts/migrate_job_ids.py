#!/usr/bin/env python3
"""Re-key jobs whose stored SQLite id differs from the canonical stable job id."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agentzero.config import get_settings
from agentzero.storage.db import Database
from agentzero.storage.job_id_migration import find_stale_job_keys, migrate_stale_job_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned rekeys without writing to the database",
    )
    args = parser.parse_args()

    settings = get_settings()
    db = Database(settings.db_path)
    try:
        stale = find_stale_job_keys(db)
        print(f"Found {len(stale)} stale job_id(s)", flush=True)
        result = migrate_stale_job_ids(db, dry_run=args.dry_run)
        for line in result.details:
            print(f"  {line}", flush=True)
        action = "Would rekey" if args.dry_run else "Rekeyed"
        print(
            f"\n{action}: {result.rekeyed}, merged: {result.merged}, "
            f"skipped: {result.skipped}",
            flush=True,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
