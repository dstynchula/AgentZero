#!/usr/bin/env python3
"""Print LLM cost estimates for the current ``.env`` / résumé search profile."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentzero.config import get_settings  # noqa: E402
from agentzero.cost.estimate import (  # noqa: E402
    MODEL_PRICING,
    PRICING_AS_OF,
    estimate_run_cost,
    estimate_unique_jobs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estimate LLM cost per AgentZero scrape+rank run (USD)."
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="Override estimated unique jobs ranked (default: from .env heuristics)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Show one model only (default: compare common models)",
    )
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    low, high = estimate_unique_jobs(settings)
    jobs = args.jobs if args.jobs is not None else (low + high) // 2

    print(f"AgentZero LLM cost estimate (pricing as of {PRICING_AS_OF.isoformat()})")
    print(f"Configured model: {settings.llm_model} ({settings.llm_provider})")
    print(
        f"Search grid: {len(settings.search_terms)} term(s) × "
        f"{len(settings.locations)} location(s) × "
        f"{settings.results_wanted} results/query"
    )
    print(f"Heuristic unique jobs after dedupe: ~{low}-{high} (using {jobs} for table)")
    print(f"Rank description cap: {settings.rank_description_max_chars} chars")
    print()
    print("These are LLM API costs only — typically cents per run, not dollars.")
    print("JobSpy scraping is free; you pay your LLM provider for ingest + ranking.")
    print()

    models = [args.model] if args.model else [
        "gpt-5-nano",
        "gpt-4.1-nano",
        "gpt-4o-mini",
        "gpt-5.4-nano",
        "gpt-4.1-mini",
    ]

    for model in models:
        if model not in MODEL_PRICING:
            print(f"Unknown model: {model}", file=sys.stderr)
            return 1
        est = estimate_run_cost(model=model, ranked_jobs=jobs)
        marker = " (configured)" if model == settings.llm_model else ""
        print(
            f"  {model:16}  ${est.usd_low:.3f}-${est.usd_high:.3f}  "
            f"(~${est.usd_mid:.3f} mid){marker}"
        )

    print()
    print("See docs/COST_AND_MODELS.md for model selection guidance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
