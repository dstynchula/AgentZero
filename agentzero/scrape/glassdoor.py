"""Glassdoor company rating enrichment from saved HTML."""

from __future__ import annotations

import re

RATING_RE = re.compile(r'"overallRating"\s*:\s*(?P<rating>\d(?:\.\d)?)')
REVIEWS_RE = re.compile(r'"reviewCount"\s*:\s*(?P<count>\d+)')


def parse_glassdoor_company_html(html: str) -> tuple[float | None, int | None]:
    rating_match = RATING_RE.search(html)
    reviews_match = REVIEWS_RE.search(html)
    rating = float(rating_match.group("rating")) if rating_match else None
    reviews = int(reviews_match.group("count")) if reviews_match else None
    return rating, reviews
