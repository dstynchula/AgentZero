#!/usr/bin/env python3
"""Run a full scrape → validate → enrich → rank pipeline.

Usage (from repo root, venv active):

    python scripts/run_scrape.py
    python scripts/run_scrape.py --limit 20
    python scripts/run_scrape.py --skip-resume-ingest   # reuse search_profile.json
    python scripts/run_scrape.py --no-search-prompt     # CI / automation

Before scraping, you are prompted to confirm titles, locations, and salary
(see docs/SCRAPING.md). Complete any Indeed consent/CAPTCHA in the visible browser.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentzero.config import get_settings
from agentzero.ingest.resume import ingest_resume
from agentzero.ingest.search_interactive import prepare_run_search
from agentzero.ingest.search_profile import apply_search_profile, load_search_profile
from agentzero.llm.provider import build_llm_provider
from agentzero.loops.pipeline import Pipeline
from agentzero.scrape.factory import build_scrape_source
from agentzero.scrape.remote_policy import apply_remote_only_settings
from agentzero.storage.db import Database


def _print_search_settings(settings, source=None, *, verbose: bool = False) -> None:
    from agentzero.scrape.factory import describe_scrape_stack

    if source is not None:
        info = describe_scrape_stack(source, settings)
        print(f"Effective sources: {', '.join(info['sources'])}")
        if info["jobspy_sites"]:
            print(f"JobSpy sites:      {info['jobspy_sites']}")
        remote = "yes" if info["remote"] else "no"
        print(
            f"Primary query:     {info['primary_term']!r} @ {info['primary_location']!r} "
            f"(remote={remote})"
        )
        print(f"Query mode:        {'primary title only' if info['primary_query_only'] else 'all titles'}")
        print(f"Delay between:     {info['delay_seconds']}s per fetch")
    elif verbose:
        print(f"Browser sites: {settings.scrape_browser_sites}")
        print(f"JobSpy sites:  {settings.scrape_sites}")
        print(f"All titles:    {settings.search_terms}")
        print(f"Locations:     {settings.locations}")
    else:
        print(
            f"Search: {len(settings.search_terms)} title(s), "
            f"{len(settings.locations)} location(s)"
        )
    print(f"Results cap:   {settings.results_wanted}")
    if settings.salary_min is not None:
        print(
            f"Comp floor:    ${settings.salary_min:,.0f} USD/year "
            f"(keep when posted range top >= floor)"
        )


def run(
    *,
    limit: int | None,
    skip_resume_ingest: bool,
    search_prompt: bool,
    refresh_search: bool,
    verbose: bool,
) -> int:
    settings = get_settings()
    resume_profile = None

    if skip_resume_ingest:
        snapshot = load_search_profile()
        if snapshot is None:
            print(
                "ERROR: --skip-resume-ingest requires resume/search_profile.json.\n"
                "Run once without that flag, or run scripts/smoke_test.py first.",
                file=sys.stderr,
            )
            return 1
        print("Skipping résumé ingest — using saved search profile (no rank step).")
        if search_prompt:
            from agentzero.ingest.search_interactive import interactive_refine_search_profile

            snapshot = interactive_refine_search_profile(
                snapshot,
                interactive=True,
                remote_only=settings.remote_only,
            )
        settings = apply_remote_only_settings(apply_search_profile(settings, snapshot))
        llm = None
    else:
        llm = build_llm_provider()

        if search_prompt:
            from agentzero.ingest.search_interactive import require_interactive_terminal

            require_interactive_terminal()
            print("Step 1/3 — Confirm search targets (required)", flush=True)
            print("You must review titles/locations/salary before scraping starts.", flush=True)
        else:
            print("Building search profile from résumé (--no-search-prompt)", flush=True)

        effective, _ = prepare_run_search(
            settings,
            llm=llm,
            interactive=search_prompt,
            force_refresh=refresh_search,
        )
        settings = effective

        print("\nStep 2/3 — Ingesting résumé for ranking...", flush=True)
        resume_profile = ingest_resume(llm=llm, refresh_search=False)
        print(f"Candidate: {resume_profile.name or '(name not found)'}", flush=True)

    if not search_prompt:
        print(
            "\nWARNING: --no-search-prompt was used; scraping with profile/env defaults.",
            flush=True,
        )

    if limit is not None:
        settings = settings.model_copy(update={"results_wanted": limit})

    source = build_scrape_source(settings, llm=None)
    db = Database(settings.db_path)
    pipeline = Pipeline(
        db, source, settings=settings, llm=llm, max_workers=settings.max_concurrency
    )

    print("\n" + "=" * 60, flush=True)
    print("Step 3/3 — Scrape + pipeline", flush=True)
    print("=" * 60, flush=True)
    _print_search_settings(settings, source=source, verbose=verbose)
    result = pipeline.run(profile=resume_profile)

    print("\nPipeline result:")
    print(f"  scraped:     {result.scraped}")
    print(f"  quarantined: {result.quarantined}")
    print(f"  enriched:    {result.enriched}")
    print(f"  ranked:      {result.ranked}")
    if result.errors:
        print(f"  errors:      {result.errors}")

    exit_code = 0
    if result.errors:
        exit_code = 1
    elif result.scraped == 0 and not db.list_jobs():
        exit_code = 2

    jobs = db.list_jobs()[:10]
    if jobs:
        print("\nLatest jobs in DB:")
        for job in jobs:
            score = f" score={job.match_score:.2f}" if job.match_score is not None else ""
            print(f"  [{job.source}] {job.title} @ {job.company}{score}")
    else:
        print("\nNo jobs in DB yet — boards may have blocked the scrape.")
        print("See docs/SCRAPING.md (Indeed CAPTCHA, rate limits).")

    print(f"\nDatabase: {settings.db_path.resolve()}")
    print("Next: docker compose up web  →  http://localhost:8080  (or python scripts/rank_jobs.py)")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AgentZero job scrape pipeline")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override AGENTZERO_RESULTS_WANTED for this run",
    )
    parser.add_argument(
        "--skip-resume-ingest",
        action="store_true",
        help="Reuse resume/search_profile.json; skip LLM résumé parse (no rank step)",
    )
    parser.add_argument(
        "--no-search-prompt",
        action="store_true",
        help="Skip interactive titles/locations/salary prompt",
    )
    parser.add_argument(
        "--refresh-search-profile",
        action="store_true",
        help="Re-run LLM search-term extraction instead of resume/search_profile.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full search terms and locations (default: counts only)",
    )
    args = parser.parse_args()

    try:
        return run(
            limit=args.limit,
            skip_resume_ingest=args.skip_resume_ingest,
            search_prompt=not args.no_search_prompt,
            refresh_search=args.refresh_search_profile,
            verbose=args.verbose,
        )
    except ValueError as exc:
        if "Missing API key" in str(exc):
            print(
                "\nERROR: No LLM API key found.\n"
                "Set OPENAI_API_KEY (or ANTHROPIC_API_KEY) in .env.",
                file=sys.stderr,
            )
            return 1
        raise
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except RuntimeError as exc:
        if "Interactive search prompt" in str(exc) or "Could not read input" in str(exc):
            print(f"\nERROR: {exc}", file=sys.stderr)
            return 1
        raise
    except FileNotFoundError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
