"""LLM run-cost estimates for AgentZero (pricing snapshots are dated; verify before budgeting)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agentzero.config import Settings

# OpenAI list prices in USD per 1M tokens. Snapshot date is shown in docs/README.
# Anthropic Haiku shown for provider=anthropic comparisons only.
PRICING_AS_OF = date(2026, 5, 29)

MODEL_PRICING: dict[str, tuple[float, float]] = {
    # model_id: (input $/1M, output $/1M)
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5.4-mini": (0.75, 4.50),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
}

# Typical token counts from AgentZero prompts (résumé ~9k chars, job descriptions).
TOKENS_RESUME_CALL_IN = 2_450
TOKENS_RESUME_CALL_OUT = 400
TOKENS_RANK_JOB_IN = 1_800  # after description truncation (see rank_description_max_chars)
TOKENS_RANK_JOB_IN_HEAVY = 3_000  # without truncation / very long listings
TOKENS_RANK_JOB_OUT = 100
TOKENS_REPAIR_IN = 1_000
TOKENS_REPAIR_OUT = 200
REPAIR_RATE = 0.05


@dataclass(frozen=True, slots=True)
class RunCostEstimate:
    """Estimated USD cost for one scrape + rank run."""

    model: str
    ranked_jobs: int
    setup_calls: int
    input_tokens: int
    output_tokens: int
    usd_low: float
    usd_high: float
    pricing_as_of: date

    @property
    def usd_mid(self) -> float:
        return (self.usd_low + self.usd_high) / 2


def estimate_unique_jobs(
    settings: Settings,
    *,
    search_terms: list[str] | None = None,
    locations: list[str] | None = None,
) -> tuple[int, int]:
    """Heuristic unique job count after cross-query dedupe (low, high)."""
    terms = search_terms if search_terms is not None else settings.search_terms
    locs = locations if locations is not None else settings.locations
    queries = max(1, len(terms) * len(locs))
    raw_max = queries * settings.results_wanted
    if queries == 1:
        low = int(settings.results_wanted * 0.75)
        high = settings.results_wanted
    else:
        low = max(1, int(raw_max * 0.12))
        high = max(low, int(raw_max * 0.35))
    return low, high


def estimate_run_cost(
    *,
    model: str,
    ranked_jobs: int,
    setup_calls: int = 2,
    heavy_descriptions: bool = False,
) -> RunCostEstimate:
    """Estimate USD for one run at ``ranked_jobs`` stored + ranked rows."""
    if model not in MODEL_PRICING:
        known = ", ".join(sorted(MODEL_PRICING))
        raise ValueError(f"Unknown model {model!r}. Known models: {known}")

    rank_in = TOKENS_RANK_JOB_IN_HEAVY if heavy_descriptions else TOKENS_RANK_JOB_IN
    setup_in = setup_calls * TOKENS_RESUME_CALL_IN
    setup_out = setup_calls * TOKENS_RESUME_CALL_OUT
    rank_in_total = ranked_jobs * rank_in
    rank_out_total = ranked_jobs * TOKENS_RANK_JOB_OUT
    repair_jobs = ranked_jobs * REPAIR_RATE
    repair_in = int(repair_jobs * TOKENS_REPAIR_IN)
    repair_out = int(repair_jobs * TOKENS_REPAIR_OUT)

    input_low = setup_in + rank_in_total + repair_in
    output_low = setup_out + rank_out_total + repair_out
    # Band: ±15% token noise
    input_high = int(input_low * 1.15)
    output_high = int(output_low * 1.15)

    price_in, price_out = MODEL_PRICING[model]
    usd_low = (input_low / 1_000_000) * price_in + (output_low / 1_000_000) * price_out
    usd_high = (input_high / 1_000_000) * price_in + (output_high / 1_000_000) * price_out

    return RunCostEstimate(
        model=model,
        ranked_jobs=ranked_jobs,
        setup_calls=setup_calls,
        input_tokens=input_low,
        output_tokens=output_low,
        usd_low=usd_low,
        usd_high=usd_high,
        pricing_as_of=PRICING_AS_OF,
    )


def estimate_from_settings(settings: Settings | None = None) -> list[RunCostEstimate]:
    """Return cost bands for common models using settings-driven job counts."""
    from agentzero.config import get_settings

    cfg = settings or get_settings()
    low, high = estimate_unique_jobs(cfg)
    mid = (low + high) // 2
    models = [
        "gpt-5-nano",
        "gpt-4o-mini",
        "gpt-5.4-nano",
        "gpt-4.1-mini",
    ]
    return [estimate_run_cost(model=m, ranked_jobs=mid) for m in models]
