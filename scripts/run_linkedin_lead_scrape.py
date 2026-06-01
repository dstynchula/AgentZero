#!/usr/bin/env python3
"""LinkedIn-only lead scrape: probe session, scrape, rank, preview leads."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agentzero.config import get_settings
from agentzero.ingest.resume import ingest_resume
from agentzero.leads.session import (
    build_run_settings,
    check_board_sessions,
    format_lead_preview,
    job_to_preview_dict,
    run_lead_scrape,
    suggest_targets,
)
from agentzero.llm.provider import build_llm_provider
from agentzero.scrape.browser_session import session_status_message
from agentzero.storage.db import Database


def main() -> int:
    settings = get_settings()
    llm = build_llm_provider()

    print("Reading résumé and inferring search targets…", flush=True)
    targets = suggest_targets(llm)
    if targets.candidate_name:
        print(f"Candidate: {targets.candidate_name}", flush=True)
    print(targets.summary(), flush=True)
    print(flush=True)

    search_terms = [
        "Staff Security Engineer",
        "Principal Security Engineer",
        "Senior Security Engineer",
    ]
    remote_only = True
    salary_min = settings.salary_min

    base = build_run_settings(
        settings,
        targets.profile,
        search_terms=search_terms,
        remote_only=remote_only,
        salary_min=salary_min,
        primary_query_only=True,
    )
    effective = base.model_copy(
        update={
            "scrape_browser_sites": ["linkedin"],
            "scrape_sites": [],
            # Use the logged-in Chrome window (same session where Garner showed up).
            "scrape_cdp_sites": ["linkedin"],
        }
    )

    print(f"LinkedIn-only scrape: {search_terms[0]!r} (remote)", flush=True)
    print("Checking LinkedIn session…", flush=True)
    for probe in check_board_sessions(effective):
        print(session_status_message(probe.site, probe.state))
        if probe.listing_count:
            print(f"  listings visible: {probe.listing_count}")
        if probe.error:
            print(f"  error: {probe.error}", file=sys.stderr)
            return 1
        if probe.state.value != "ready":
            print(
                "LinkedIn session not ready — run: python scripts/login_job_boards.py --site linkedin",
                file=sys.stderr,
            )
            return 1

    resume = ingest_resume(llm=llm, refresh_search=False)
    db = Database(settings.db_path)
    try:
        print("\nScraping LinkedIn (new roles land as status=lead)…", flush=True)
        run = run_lead_scrape(db, effective, llm=llm, profile=resume)
        p = run.pipeline
        print(
            f"\nPipeline: scraped={p.scraped} ranked={p.ranked} "
            f"quarantined={p.quarantined} title_filtered={p.title_filtered}",
            flush=True,
        )
        if p.errors:
            print(f"Errors: {p.errors}", file=sys.stderr)
        print()
        print(format_lead_preview(run.leads))
        if run.leads:
            print("\nDetails:")
            for job in run.leads:
                d = job_to_preview_dict(job)
                score = d["match_score"]
                score_s = f"{score:.2f}" if score is not None else "—"
                loc = d["location"] or ("remote" if d["remote"] else "")
                comp = ""
                if d["comp_min"] or d["comp_max"]:
                    lo = d["comp_min"]
                    hi = d["comp_max"]
                    comp = f" ${lo:,.0f}-${hi:,.0f}" if lo and hi else ""
                print(
                    f"  [{score_s}] {d['title']} @ {d['company']}{comp} "
                    f"({loc}) id={d['job_id']}"
                )
                garner = "garner" in str(d["company"]).lower()
                if garner or "garner" in d["url"].lower():
                    print(f"    ** Garner Health match ** url={d['url']}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
