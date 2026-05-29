"""Glassdoor rating enrichment fallback."""

from __future__ import annotations

import re

from agentzero.models import JobPosting

RATING_IN_TEXT_RE = re.compile(
    r"glassdoor\s+rating[:\s]+(?P<rating>\d(?:\.\d)?)",
    re.IGNORECASE,
)


def parse_rating_from_description(description: str) -> float | None:
    match = RATING_IN_TEXT_RE.search(description)
    if not match:
        return None
    return float(match.group("rating"))


def enrich_glassdoor(job: JobPosting) -> JobPosting:
    if job.glassdoor_rating is not None:
        return job
    if not job.description:
        return job
    rating = parse_rating_from_description(job.description)
    if rating is None:
        return job
    return job.model_copy(update={"glassdoor_rating": rating})
