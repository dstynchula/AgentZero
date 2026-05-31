#!/usr/bin/env python3
"""Rank jobs in SQLite against your résumé, then push to Google Sheets.

Usage:

    python scripts/rank_and_sync.py
    python scripts/rank_and_sync.py --skip-sync    # rank only
    python scripts/rank_and_sync.py --sync-only --yes  # sheet export only (no LLM)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _rank_all(
    *,
    db,
    llm,
    profile,
    max_workers: int,
    force: bool,
    max_description_chars: int,
) -> tuple[int, int]:
    """Return ``(ranked_count, error_count)``."""
    from agentzero.enrich.pipeline import enrich_job
    from agentzero.loops.progress import Progress
    from agentzero.loops.ralph import run_parallel
    from agentzero.rank.matcher import rank_job
    from agentzero.storage.csv_export import match_tier

    errors = 0

    def enrich_one(job_id: str) -> None:
        job = db.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        enriched = enrich_job(job)
        db.upsert_job(enriched)
        db.mark_pipeline(job_id, "enrich_status", "done")

    pending_enrich = db.list_pending("enrich_status")
    if pending_enrich:
        enrich_progress = Progress(len(pending_enrich), label="Enrich")
        enrich_progress.announce()
        enrich_failures = run_parallel(
            pending_enrich,
            enrich_one,
            max_workers=max_workers,
            progress=enrich_progress,
            item_label=lambda jid: _job_label(db, jid),
        )
        enrich_progress.finish()
        errors += len(enrich_failures)

    if force:
        job_ids = [j.job_id for j in db.list_jobs()]
    else:
        job_ids = db.list_pending("rank_status")
        if not job_ids:
            already = sum(1 for j in db.list_jobs() if j.match_score is not None)
            print(f"All {already} job(s) already ranked. Use --force to re-classify.")
            return already, errors

    if not job_ids:
        print("No jobs in database.")
        return 0, errors

    print(f"Ranking with {max_workers} parallel LLM worker(s)…", flush=True)
    rank_progress = Progress(len(job_ids), label="Rank")
    rank_progress.announce("LLM fit score per job")

    def rank_one(job_id: str) -> None:
        job = db.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        match = rank_job(
            job,
            profile,
            llm=llm,
            max_description_chars=max_description_chars,
        )
        updated = job.model_copy(
            update={
                "match_score": match.match_score,
                "match_rationale": match.rationale,
            },
        )
        db.upsert_job(updated)
        db.mark_pipeline(job_id, "rank_status", "done")

    def rank_label(job_id: str) -> str:
        job = db.get_job(job_id)
        if job is None:
            return job_id
        refreshed = db.get_job(job_id)
        score = refreshed.match_score if refreshed else None
        base = f"{job.title} @ {job.company}"
        if score is not None:
            return f"{base} -> {score:.2f} ({match_tier(score)})"
        return base

    failures = run_parallel(
        job_ids,
        rank_one,
        max_workers=max_workers,
        progress=rank_progress,
        item_label=rank_label,
    )
    rank_progress.finish()
    errors += len(failures)
    if failures:
        print(f"\nWARNING: {len(failures)} rank failure(s):", flush=True)
        for msg in failures[:5]:
            print(f"  - {msg}", flush=True)
        if len(failures) > 5:
            print(f"  … and {len(failures) - 5} more", flush=True)

    ranked = [j for j in db.list_jobs() if j.match_score is not None]
    ranked.sort(key=lambda j: j.match_score or 0.0, reverse=True)
    print("\nTop matches:")
    for job in ranked[:10]:
        tier = match_tier(job.match_score)
        print(f"  [{tier}] {job.match_score:.2f} — {job.title} @ {job.company}")
    return len(ranked), errors


def _job_label(db, job_id: str) -> str:
    job = db.get_job(job_id)
    if job is None:
        return job_id
    return f"{job.title} @ {job.company}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank jobs and sync to Google Sheets")
    parser.add_argument("--skip-sync", action="store_true", help="Rank only; no Sheets write")
    parser.add_argument("--sync-only", action="store_true", help="Push DB to Sheet without ranking")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive worksheet clear+rewrite when syncing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-rank all jobs (default: only jobs not yet ranked)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel rank workers (default: AGENTZERO_RANK_MAX_CONCURRENCY)",
    )
    parser.add_argument("--db", type=Path, default=None, help="SQLite path override")
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.storage.db import Database

    settings = get_settings()
    db_path = args.db or settings.db_path
    if not db_path.is_file():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1

    db = Database(db_path)
    errors = 0

    if not args.sync_only:
        from agentzero.ingest.resume import ingest_resume
        from agentzero.llm.provider import build_llm_provider

        llm = build_llm_provider()
        print("Loading résumé (LLM parse, ~15-30s)…", flush=True)
        profile = ingest_resume(llm=llm, refresh_search=False)
        print(f"Candidate: {profile.name or '(unknown)'}\n", flush=True)
        workers = args.workers if args.workers is not None else settings.rank_max_concurrency
        workers = max(1, workers)
        count, errors = _rank_all(
            db=db,
            llm=llm,
            profile=profile,
            max_workers=workers,
            force=args.force,
            max_description_chars=settings.rank_description_max_chars,
        )
        if count == 0 and not args.force:
            return 1 if errors else 0

    if args.skip_sync:
        print("\nSkipping Google Sheets (--skip-sync).")
        return 1 if errors else 0

    if not args.yes:
        print(
            "\nERROR: sync clears the entire worksheet. Pass --yes to confirm, or --skip-sync.",
            file=sys.stderr,
        )
        print("Preview row count: python scripts/sync_sheets.py --dry-run", file=sys.stderr)
        return 1

    if not settings.sheet_id:
        print("ERROR: AGENTZERO_SHEET_ID not set in .env", file=sys.stderr)
        return 1
    if not settings.google_token_path.is_file():
        print(
            f"ERROR: {settings.google_token_path} missing. "
            "Run: python scripts/google_auth.py",
            file=sys.stderr,
        )
        return 1

    from agentzero.google.sync import sync_jobs_to_sheet

    job_count = db.count_jobs()
    from agentzero.rank.export_filter import filter_jobs_for_export

    export_jobs, below_floor = filter_jobs_for_export(db.list_jobs(), settings.min_match_score)
    print(f"\nSyncing {len(export_jobs)} job(s) to Google Sheet", end="", flush=True)
    if below_floor and settings.min_match_score:
        print(
            f" ({job_count} in DB; {len(below_floor)} below "
            f"min match_score {settings.min_match_score:g})",
            end="",
            flush=True,
        )
    print("…", flush=True)
    try:
        result = sync_jobs_to_sheet(db=db, settings=settings)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if result.imported:
        print(f"Imported user fields for {result.imported} job(s) from the sheet.", flush=True)
    print(
        f"OK - synced {result.row_count} row(s) to {result.spreadsheet_title!r} "
        "(sorted by match_score, High/Medium/Low tier)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
