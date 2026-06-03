#!/usr/bin/env python3
"""Print scrape input settings and per-stage drop counts (matches web UI path)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    from agentzero.scrape.comp_filter import filter_by_salary_floor
    from agentzero.scrape.factory import build_scrape_source
    from agentzero.scrape.linkedin_jobs import LinkedInJobsService
    from agentzero.scrape.remote_policy import job_is_remote
    from agentzero.scrape.scrape_query_params import iter_scrape_queries
    from agentzero.scrape.title_filter import filter_by_title_relevance
    from agentzero.scrape.validate import validate_batch
    from agentzero.web.scrape_settings import build_web_scrape_settings

    cfg = build_web_scrape_settings()

    out: dict = {
        "input": {
            "search_terms": cfg.search_terms,
            "locations": cfg.locations,
            "remote_only": cfg.remote_only,
            "salary_min": cfg.salary_min,
            "results_wanted": cfg.results_wanted,
            "scrape_primary_query_only": cfg.scrape_primary_query_only,
            "browser_sites": cfg.scrape_browser_sites,
            "headless": cfg.scrape_browser_headless,
            "browser_channel": cfg.scrape_browser_channel or "",
        },
        "queries": [
            {"term": t, "location": p.raw, "remote": p.is_remote}
            for t, p in iter_scrape_queries(cfg)
        ],
    }

    print("=== LinkedIn fetch (browser) ===", flush=True)
    result = LinkedInJobsService(cfg).search()
    out["linkedin_fetch"] = {
        "parsed_raw": result.parsed_raw,
        "after_title_filter": result.after_title_filter,
        "records_returned": len(result.records),
        "cap": cfg.results_wanted,
        "session_state": result.session_state,
        "login_required": result.login_required,
        "error": result.error,
    }
    raw = list(build_scrape_source(cfg).fetch())
    out["fetch_records"] = len(raw)

    jobs, quarantined, metrics = validate_batch(raw, source="linkedin_browser", llm=None)
    remote_rej = [j for j in jobs if not job_is_remote(j)]
    jobs_r = [j for j in jobs if job_is_remote(j)]
    title_kept, title_rej = filter_by_title_relevance(jobs_r, cfg.search_terms)
    comp_kept, comp_rej = filter_by_salary_floor(title_kept, cfg.salary_min)
    unknown_comp = sum(1 for j in title_kept if j.comp_min is None and j.comp_max is None)

    out["pipeline"] = {
        "valid": len(jobs),
        "quarantined": len(quarantined),
        "quarantine_samples": [q[1] for q in quarantined[:3]],
        "remote_dropped": len(remote_rej),
        "title_dropped": len(title_rej),
        "title_drop_samples": [f"{j.title} @ {j.company}" for j in title_rej[:5]],
        "comp_dropped": len(comp_rej),
        "comp_drop_samples": [
            f"{j.title} ({j.comp_min}-{j.comp_max})" for j in comp_rej[:5]
        ],
        "unknown_comp_kept": unknown_comp,
        "final_kept": len(comp_kept),
        "unique_job_ids": len({j.job_id for j in comp_kept}),
    }
    summary = {
        "input": out["input"],
        "queries": out["queries"],
        "linkedin_fetch": {
            k: out["linkedin_fetch"][k]
            for k in (
                "parsed_raw",
                "after_title_filter",
                "records_returned",
                "cap",
                "login_required",
            )
        },
        "fetch_records": out["fetch_records"],
        "pipeline": out["pipeline"],
    }
    report_path = REPO / "data" / "scrape_diagnose_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote scrape diagnose report to {report_path}", flush=True)
    return 0 if comp_kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
