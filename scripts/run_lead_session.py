#!/usr/bin/env python3
"""Interactive lead-gathering session: suggest targets, scrape, review, commit.

Usage (from repo root, venv active):

    python scripts/run_lead_session.py
    python scripts/run_lead_session.py --titles "Staff Security Engineer,Principal Security Engineer"
    python scripts/run_lead_session.py --yes   # skip approval prompt, commit all leads

The agent/MCP counterpart lives in ``agentzero/mcp_server.py`` (same core module).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _split_csv(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _parse_optional_float(text: str) -> float | None:
    cleaned = text.strip().replace(",", "").replace("$", "")
    if not cleaned or cleaned.lower() in {"none", "(none)"}:
        return None
    return float(cleaned)


def _prompt(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive lead-gathering scrape session")
    parser.add_argument(
        "--titles",
        default="",
        help="Comma-separated job titles (skips title prompt)",
    )
    parser.add_argument(
        "--remote-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Remote USA only (default: from .env / résumé)",
    )
    parser.add_argument(
        "--min-comp",
        type=float,
        default=None,
        help="Minimum comp floor USD/year",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override AGENTZERO_RESULTS_WANTED",
    )
    parser.add_argument(
        "--all-titles",
        action="store_true",
        help="Query every title (not just the first)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Approve and sync all new leads without prompting",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="List pending leads only (no scrape)",
    )
    args = parser.parse_args()

    from agentzero.config import get_settings
    from agentzero.ingest.resume import ingest_resume
    from agentzero.leads.session import (
        approve_leads,
        build_run_settings,
        check_board_sessions,
        commit_leads,
        format_lead_preview,
        list_pending_leads,
        run_lead_scrape,
        suggest_targets,
    )
    from agentzero.llm.provider import build_llm_provider
    from agentzero.scrape.browser_session import session_status_message
    from agentzero.storage.db import Database

    settings = get_settings()
    llm = build_llm_provider()

    print("Reading résumé and inferring search targets…", flush=True)
    targets = suggest_targets(llm)
    print(targets.safe_log_line(), flush=True)
    print("Confirm search parameters at the prompts below.", flush=True)
    print(flush=True)

    if args.skip_scrape:
        db = Database(settings.db_path)
        try:
            leads = list_pending_leads(db)
            print(format_lead_preview(leads))
        finally:
            db.close()
        return 0

    titles_raw = args.titles or _prompt(
        "Job titles",
        ", ".join(targets.search_terms),
    )
    search_terms = _split_csv(titles_raw)
    if not search_terms:
        print("ERROR: at least one job title is required.", file=sys.stderr)
        return 1

    remote_default = "yes" if (args.remote_only if args.remote_only is not None else settings.remote_only) else "no"
    if args.remote_only is None:
        remote_raw = _prompt("Remote-only? (yes/no)", remote_default).lower()
        remote_only = remote_raw not in {"n", "no", "false", "0"}
    else:
        remote_only = args.remote_only

    floor_default = (
        f"{int(targets.salary_min):,}" if targets.salary_min is not None else "none"
    )
    if args.min_comp is None:
        floor_raw = _prompt("Minimum comp USD/year (none=off)", floor_default)
        salary_min = _parse_optional_float(floor_raw)
    else:
        salary_min = args.min_comp

    effective = build_run_settings(
        settings,
        targets.profile,
        search_terms=search_terms,
        remote_only=remote_only,
        salary_min=salary_min,
        results_wanted=args.limit,
        primary_query_only=not args.all_titles,
    )

    print("\nChecking browser sessions…", flush=True)
    from agentzero.scrape.browser_common import ensure_cdp_for_sites

    try:
        ensure_cdp_for_sites(effective)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for probe in check_board_sessions(effective):
        print(session_status_message(probe.site, probe.state))
        if probe.listing_count:
            print(f"  listings visible: {probe.listing_count}")
        if probe.error:
            print(f"  error: {probe.error}", file=sys.stderr)

    confirm = _prompt("\nType YES to start scraping", "").lower()
    if confirm != "yes":
        print("Cancelled.")
        return 0

    resume = ingest_resume(llm=llm, refresh_search=False)
    db = Database(settings.db_path)
    try:
        print("\nScraping (new roles land as lead, not on sheet yet)…", flush=True)
        run = run_lead_scrape(db, effective, llm=llm, profile=resume)
        print(f"\nPipeline: scraped={run.pipeline.scraped} ranked={run.pipeline.ranked}")
        if run.pipeline.errors:
            print(f"Errors: {run.pipeline.errors}", file=sys.stderr)
        print()
        print(format_lead_preview(run.leads))

        if not run.leads:
            return 0

        if args.yes:
            job_ids = [job.job_id for job in run.leads]
            if settings.sheet_id:
                commit = commit_leads(db, settings, job_ids)
                print(
                    f"\nCommitted {commit.approved} lead(s) to "
                    f"{commit.sync.spreadsheet_title!r}."
                )
            else:
                count = approve_leads(db, job_ids)
                print(f"\nApproved {count} lead(s) (no AGENTZERO_SHEET_ID — DB only).")
            return 0

        answer = _prompt(
            "Approve leads? (all / none / comma-separated job_ids)",
            "none",
        ).strip().lower()
        if answer in {"", "none", "n", "no"}:
            print("Leads kept as status=lead in the DB for later review.")
            return 0

        if answer == "all":
            job_ids = [job.job_id for job in run.leads]
        else:
            job_ids = _split_csv(answer)

        if settings.sheet_id:
            commit = commit_leads(db, settings, job_ids)
            print(
                f"Committed {commit.approved} lead(s) to {commit.sync.spreadsheet_title!r} "
                f"({commit.sync.row_count} rows)."
            )
        else:
            count = approve_leads(db, job_ids)
            print(f"Approved {count} lead(s) (set AGENTZERO_SHEET_ID to sync).")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        raise SystemExit(130) from None
    except ValueError as exc:
        if "Missing API key" in str(exc):
            print("ERROR: Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env.", file=sys.stderr)
            raise SystemExit(1) from exc
        raise
