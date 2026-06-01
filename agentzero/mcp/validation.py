"""Input validation for MCP-exposed tools."""

from __future__ import annotations

_MAX_SEARCH_TERMS = 12
_MAX_TERM_LEN = 120
_MAX_RESULTS_WANTED = 200
_MIN_SALARY = 0.0
_MAX_SALARY = 10_000_000.0
_MAX_JOB_IDS = 500


def validate_scrape_tool_args(
    search_terms: list[str],
    *,
    salary_min: float | None,
    results_wanted: int | None,
) -> list[str]:
    """Normalize and validate ``run_scrape`` inputs; raise ``ValueError`` on abuse."""
    if not search_terms:
        raise ValueError("search_terms must contain at least one title")
    if len(search_terms) > _MAX_SEARCH_TERMS:
        raise ValueError(f"search_terms limited to {_MAX_SEARCH_TERMS} items")
    cleaned: list[str] = []
    for raw in search_terms:
        term = raw.strip()
        if not term:
            continue
        if len(term) > _MAX_TERM_LEN:
            raise ValueError(f"search term too long (max {_MAX_TERM_LEN} chars): {term[:40]!r}…")
        cleaned.append(term)
    if not cleaned:
        raise ValueError("search_terms must contain at least one non-empty title")
    if salary_min is not None and not (_MIN_SALARY <= salary_min <= _MAX_SALARY):
        raise ValueError(f"salary_min must be between {_MIN_SALARY} and {_MAX_SALARY:,.0f}")
    if results_wanted is not None:
        if results_wanted < 1:
            raise ValueError("results_wanted must be >= 1")
        if results_wanted > _MAX_RESULTS_WANTED:
            raise ValueError(f"results_wanted limited to {_MAX_RESULTS_WANTED}")
    return cleaned


def validate_job_ids(job_ids: list[str]) -> list[str]:
    """Dedupe and cap job id lists for approve/reject/commit tools."""
    if not job_ids:
        raise ValueError("job_ids must not be empty")
    if len(job_ids) > _MAX_JOB_IDS:
        raise ValueError(f"job_ids limited to {_MAX_JOB_IDS} items")
    seen: set[str] = set()
    out: list[str] = []
    for raw in job_ids:
        jid = raw.strip()
        if not jid or jid in seen:
            continue
        seen.add(jid)
        out.append(jid)
    if not out:
        raise ValueError("job_ids must contain at least one non-empty id")
    return out
