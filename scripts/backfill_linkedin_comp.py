#!/usr/bin/env python3
"""Backfill missing comp via LinkedIn job detail pages, then re-sync sheet."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agentzero.config import get_settings
from agentzero.enrich.comp import enrich_comp
from agentzero.enrich.detail_fetch import fetch_and_merge_detail
from agentzero.storage.db import Database


def main() -> int:
    settings = get_settings().model_copy(update={"scrape_cdp_sites": ["linkedin"]})
    db = Database(settings.db_path)
    try:
        targets = [
            job
            for job in db.list_jobs()
            if "linkedin" in job.source.lower()
            and job.comp_min is None
            and job.comp_max is None
        ]
        print(f"Backfilling comp for {len(targets)} LinkedIn job(s)…", flush=True)
        updated = 0
        for index, job in enumerate(targets, start=1):
            print(f"  [{index}/{len(targets)}] {job.title} @ {job.company}", flush=True)
            merged = fetch_and_merge_detail(job, settings=settings, allow_browser=True)
            merged = enrich_comp(merged)
            if merged.comp_min or merged.comp_max:
                db.upsert_job(merged)
                updated += 1
                lo = f"${merged.comp_min:,.0f}" if merged.comp_min else "?"
                hi = f"${merged.comp_max:,.0f}" if merged.comp_max else "?"
                print(f"    -> {lo} - {hi}", flush=True)
            else:
                print("    -> (no comp found on detail page)", flush=True)

        print(f"\nUpdated comp on {updated}/{len(targets)} job(s).", flush=True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
