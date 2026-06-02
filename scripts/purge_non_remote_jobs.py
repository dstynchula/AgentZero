#!/usr/bin/env python3
"""Remove non-remote jobs from SQLite.

Usage:

    python scripts/purge_non_remote_jobs.py --dry-run
    python scripts/purge_non_remote_jobs.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete non-remote jobs from SQLite")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--yes", action="store_true", help="Delete from database")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("ERROR: pass --dry-run or --yes", file=sys.stderr)
        return 1

    from agentzero.apply.tracking import is_application_locked
    from agentzero.config import get_settings
    from agentzero.scrape.remote_policy import job_is_remote
    from agentzero.storage.db import Database

    settings = get_settings()
    db = Database(args.db or settings.db_path)
    jobs = db.list_jobs()
    to_delete = [j for j in jobs if not job_is_remote(j) and not is_application_locked(j)]
    protected = sum(1 for j in jobs if not job_is_remote(j) and is_application_locked(j))
    to_keep = len(jobs) - len(to_delete)

    print(f"Total jobs: {len(jobs)}")
    print(f"Remote (keep): {to_keep}")
    print(f"Non-remote (remove): {len(to_delete)}")
    if protected:
        print(f"Non-remote but applied (protected): {protected}")
    for job in to_delete[:15]:
        loc = job.location or "(no location)"
        print(f"  - {job.title} @ {job.company} [{loc}]")
    if len(to_delete) > 15:
        print(f"  … and {len(to_delete) - 15} more")

    if args.dry_run:
        return 0

    deleted = db.delete_jobs([j.job_id for j in to_delete])
    print(f"\nDeleted {deleted} job(s) from {db.path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
