#!/usr/bin/env python3
"""Resolve Unknown Glassdoor employers and re-sync the tracker sheet."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agentzero.config import get_settings
from agentzero.scrape.glassdoor_company import resolve_glassdoor_company
from agentzero.storage.db import Database


def _is_unknown(company: str) -> bool:
    return company.strip().lower() in {"", "unknown"}


def main() -> int:
    settings = get_settings()
    db = Database(settings.db_path)
    try:
        targets = [
            job
            for job in db.list_jobs()
            if "glassdoor" in job.source.lower() and _is_unknown(job.company)
        ]
        print(f"Resolving company for {len(targets)} Glassdoor job(s)…", flush=True)
        resolved = 0
        for index, job in enumerate(targets, start=1):
            company = resolve_glassdoor_company(
                title=job.title,
                url=job.url,
                description=job.description or "",
            )
            if not company:
                print(f"  [{index}/{len(targets)}] still unknown: {job.title}", flush=True)
                continue

            updated = job.model_copy(update={"company": company})
            old_id = job.job_id
            db.upsert_job(updated)
            if updated.job_id != old_id:
                db.delete_jobs([old_id])
            resolved += 1
            print(f"  [{index}/{len(targets)}] {job.title} -> {company}", flush=True)

        print(f"\nResolved {resolved}/{len(targets)}.", flush=True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
