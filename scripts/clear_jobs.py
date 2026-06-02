#!/usr/bin/env python3
"""Clear scraped jobs from SQLite.

Usage:

    python scripts/clear_jobs.py
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
