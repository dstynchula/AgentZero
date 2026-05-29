"""Compensation parsing and estimation from job descriptions."""

from __future__ import annotations

import re

from agentzero.models import JobPosting
from agentzero.scrape.validate import parse_comp_from_text

# Patterns like "150 employees" or "10,001+ employees"
EMPLOYEE_COUNT_RE = re.compile(
    r"(?P<count>[\d,]+)\+?\s*(?:employees|staff|people)",
    re.IGNORECASE,
)


def parse_comp_from_description(description: str) -> tuple[float | None, float | None, str | None]:
    """Extract salary range from free-text description."""
    return parse_comp_from_text(description)


def enrich_comp(job: JobPosting) -> JobPosting:
    """Fill missing comp fields from the description; mark estimates explicitly."""
    if job.comp_min is not None or job.comp_max is not None:
        return job
    if not job.description:
        return job
    try:
        low, high, currency = parse_comp_from_description(job.description)
    except ValueError:
        return job
    if low is None and high is None:
        return job
    return job.model_copy(
        update={
            "comp_min": low,
            "comp_max": high,
            "currency": currency or job.currency,
            "comp_is_estimate": True,
        }
    )


def parse_employee_count(text: str) -> int | None:
    """Parse employee count from text for company-size estimation."""
    match = EMPLOYEE_COUNT_RE.search(text)
    if not match:
        return None
    return int(match.group("count").replace(",", ""))
