#!/usr/bin/env python3
"""Debug LinkedIn job search locally — JSON summary and optional HTML snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug LinkedIn search scrape")
    parser.add_argument(
        "--terms",
        default=None,
        help="One title, or comma-separated list (ignored with --use-operator-config)",
    )
    parser.add_argument(
        "--locations",
        default="Remote - USA",
        help="Location string for search (ignored with --use-operator-config)",
    )
    parser.add_argument("--remote", action="store_true", help="Add LinkedIn remote filter f_WT=2")
    parser.add_argument(
        "--use-operator-config",
        action="store_true",
        help="Use data/web_operator_config.json + search profile (same as web Scraper scrape)",
    )
    parser.add_argument(
        "--all-titles",
        action="store_true",
        help="Run every AGENTZERO_SEARCH_TERMS entry (sets scrape_primary_query_only=false)",
    )
    parser.add_argument(
        "--cdp",
        action="store_true",
        help="Force CDP Chrome for LinkedIn (else Playwright profile)",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Save last page HTML under data/debug/ (gitignored)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved settings only; do not launch browser",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Required for real browser fetch (safety guard)",
    )
    return parser


def _parse_terms_arg(raw: str | None) -> list[str]:
    if not raw:
        return ["Staff Security Engineer"]
    return [part.strip() for part in raw.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    from agentzero.config import get_settings
    from agentzero.scrape.scrape_query_params import iter_scrape_queries

    base = get_settings()

    if args.use_operator_config:
        from agentzero.web.scrape_settings import build_web_scrape_settings

        settings = build_web_scrape_settings(base)
    else:
        terms = _parse_terms_arg(args.terms)
        updates: dict = {
            "search_terms": terms,
            "locations": [args.locations],
            "remote_only": args.remote,
            "scrape_browser_sites": ["linkedin"],
            "scrape_session_preflight": True,
            "scrape_primary_query_only": False if (args.all_titles or len(terms) > 1) else True,
        }
        if args.cdp:
            updates["scrape_cdp_sites"] = ["linkedin"]
        else:
            updates["scrape_cdp_sites"] = [
                s for s in base.scrape_cdp_sites if s.lower() != "linkedin"
            ]
        settings = base.model_copy(update=updates)

    from agentzero.scrape.browser_common import browser_profile_dir

    queries = iter_scrape_queries(settings)
    summary: dict = {
        "terms": settings.search_terms,
        "queries_planned": [{"term": t, "location": p.raw} for t, p in queries],
        "scrape_primary_query_only": settings.scrape_primary_query_only,
        "locations": settings.locations,
        "remote_only": settings.remote_only,
        "salary_min": settings.salary_min,
        "results_wanted": settings.results_wanted,
        "headless": settings.scrape_browser_headless,
        "cdp_sites": settings.scrape_cdp_sites,
        "cdp_url": settings.scrape_cdp_url or "",
        "profile_dir": str(browser_profile_dir(settings, "linkedin")),
        "use_operator_config": args.use_operator_config,
    }

    if args.dry_run:
        print(json.dumps({"dry_run": True, **summary}, indent=2))
        return 0

    if not args.live:
        print(
            "Refusing live browser without --live. Use --dry-run for settings only.",
            file=sys.stderr,
        )
        return 2

    from agentzero.scrape.linkedin_jobs import LinkedInJobsService

    service = LinkedInJobsService(settings)
    result = service.search()

    out = {
        **summary,
        "url": result.url,
        "login_required": result.login_required,
        "error": result.error,
        "session_state": result.session_state,
        "has_job_markers": result.has_job_markers,
        "parsed_raw": result.parsed_raw,
        "after_title_filter": result.after_title_filter,
        "count": len(result.records),
        "titles": [str(r.get("title", "")) for r in result.records[:10]],
    }
    print(json.dumps(out, indent=2))

    if args.snapshot and result.html_snapshot:
        debug_dir = REPO / "data" / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = debug_dir / f"linkedin_search_{stamp}.html"
        path.write_text(result.html_snapshot, encoding="utf-8")
        print(f"Snapshot: {path}", file=sys.stderr)

    if result.login_required:
        return 1
    if result.error:
        return 3
    if (result.after_title_filter or 0) < 1:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
