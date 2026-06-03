#!/usr/bin/env python3
"""Smoke-test AgentZero against the résumé in ``resume/``.

Usage (from repo root, venv active):

    python scripts/smoke_test.py              # résumé read + LLM ingest + search profile
    python scripts/smoke_test.py --resume-only
    python scripts/smoke_test.py --scrape     # also fetch a small JobSpy batch + pipeline
    python scripts/smoke_test.py --scrape --limit 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _print_header(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def step_read_resume() -> tuple[Path, str]:
    from agentzero.ingest.resume import find_latest_resume, read_resume_text

    path = find_latest_resume()
    text = read_resume_text(path)
    _print_header("1. Read résumé")
    print(f"File:   {path.name}")
    print(f"Chars:  {len(text)}")
    preview = text[:200].strip()
    if len(text) > 200:
        preview += "…"
    print(f"Preview:\n{preview}")
    return path, text


def step_ingest_resume() -> object:
    from agentzero.ingest.resume import ingest_resume
    from agentzero.ingest.search_profile import load_search_profile
    from agentzero.llm.provider import build_llm_provider

    llm = build_llm_provider()
    _print_header("2. LLM résumé ingest + search profile")
    profile = ingest_resume(llm=llm)
    print(f"Name:       {profile.name or '(not found)'}")
    if profile.email:
        local, _, domain = profile.email.partition("@")
        masked = f"{local[:2]}***@{domain}" if local else profile.email
        print(f"Email:      {masked}")
    skills_preview = ", ".join(profile.skills[:12])
    if len(profile.skills) > 12:
        skills_preview += "..."
    print(f"Skills:     {skills_preview}")
    if profile.experience:
        print("Recent roles (newest first):")
        for role in profile.experience[:5]:
            company = f" @ {role.company}" if role.company else ""
            print(f"  - {role.title}{company}")
    snapshot = load_search_profile()
    if snapshot is not None:
        print("\nSearch profile snapshot:")
        print(f"  Titles:     {', '.join(snapshot.search_terms)}")
        print(f"  Locations:  {', '.join(snapshot.locations)}")
        if snapshot.salary_min is not None:
            print("  Comp floor: (configured)")
    return profile


def step_scrape(*, limit: int, profile: object | None, search_prompt: bool) -> int:
    from agentzero.config import get_settings
    from agentzero.ingest.search_interactive import prepare_run_search
    from agentzero.llm.provider import build_llm_provider
    from agentzero.loops.pipeline import Pipeline
    from agentzero.scrape.factory import build_scrape_source
    from agentzero.storage.db import Database

    settings = get_settings()
    llm = build_llm_provider()
    effective, _search_profile = prepare_run_search(
        settings,
        llm=llm,
        interactive=search_prompt,
    )
    settings = effective.model_copy(update={"results_wanted": limit})
    source = build_scrape_source(settings, llm=None)

    _print_header(f"3. Scrape + pipeline (limit={limit})")
    print(f"Browser sites: {settings.scrape_browser_sites}")
    print(f"JobSpy sites:  {settings.scrape_sites}")
    print(f"Search terms:  {settings.search_terms}")
    print(f"Locations:     {settings.locations}")
    if settings.salary_min is not None:
        print("Comp floor:    (configured)")

    db = Database(settings.db_path)
    pipeline = Pipeline(db, source, settings=settings, llm=llm, max_workers=2)
    result = pipeline.run(profile=profile)

    print("\nPipeline result:")
    print(f"  scraped:     {result.scraped}")
    print(f"  quarantined: {result.quarantined}")
    print(f"  enriched:    {result.enriched}")
    print(f"  ranked:      {result.ranked}")
    if result.errors:
        print(f"  errors:      {result.errors}")
        return 1

    jobs = db.list_jobs()[:5]
    if jobs:
        print("\nTop rows in DB:")
        for job in jobs:
            score = f" score={job.match_score:.2f}" if job.match_score is not None else ""
            print(f"  [{job.source}] {job.title} @ {job.company}{score}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test AgentZero with resume/")
    parser.add_argument(
        "--resume-only",
        action="store_true",
        help="Only read the résumé file (no LLM, no scrape)",
    )
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Run a small JobSpy fetch + validate/enrich/rank pipeline",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max JobSpy results for --scrape (default: 5)",
    )
    parser.add_argument(
        "--no-search-prompt",
        action="store_true",
        help="Skip interactive titles/locations/salary prompt before --scrape",
    )
    args = parser.parse_args()

    try:
        step_read_resume()
        if args.resume_only:
            print("\nOK — résumé read succeeded (no LLM).")
            return 0

        profile = step_ingest_resume()
        if args.scrape:
            search_prompt = not args.no_search_prompt
            if step_scrape(limit=args.limit, profile=profile, search_prompt=search_prompt) != 0:
                return 1

        print("\nOK — smoke test complete.")
        if not args.scrape:
            print(
                "Tip: add --scrape to fetch a few live jobs into SQLite."
            )
        return 0
    except ValueError as exc:
        if "Missing API key" in str(exc):
            print(
                "\nERROR: No LLM API key found.\n"
                "Copy .env.example to .env and set OPENAI_API_KEY (or ANTHROPIC_API_KEY).\n"
                "Then re-run: python scripts/smoke_test.py",
                file=sys.stderr,
            )
            return 1
        raise
    except FileNotFoundError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
