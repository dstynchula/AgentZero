"""Look up company rating/review count from Glassdoor search HTML."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from agentzero.models import JobPosting
from agentzero.net.http_client import safe_get_text
from agentzero.scrape.glassdoor import parse_glassdoor_company_html

log = logging.getLogger(__name__)


def glassdoor_search_url(company: str) -> str:
    q = quote_plus(company.strip())
    return f"https://www.glassdoor.com/Reviews/company-reviews.htm?suggestCount=0&typedKeyword={q}&sc.keyword={q}"


def fetch_glassdoor_company_html(company: str, *, user_agent: str) -> str | None:
    url = glassdoor_search_url(company)
    return safe_get_text(url, user_agent=user_agent, timeout=25.0)


def parse_glassdoor_from_page(html: str) -> tuple[float | None, int | None]:
    rating, reviews = parse_glassdoor_company_html(html)
    if rating is not None:
        return rating, reviews
    rating_m = re.search(r'"rating"\s*:\s*(?P<r>\d(?:\.\d)?)', html)
    reviews_m = re.search(r'"reviewCount"\s*:\s*(?P<c>\d+)', html)
    r = float(rating_m.group("r")) if rating_m else None
    c = int(reviews_m.group("c")) if reviews_m else None
    return r, c


def _company_lookupable(company: str) -> bool:
    cleaned = company.strip()
    return bool(cleaned) and cleaned.lower() != "unknown"


def enrich_glassdoor_company(
    job: JobPosting,
    *,
    user_agent: str,
) -> JobPosting:
    if job.glassdoor_rating is not None and job.glassdoor_reviews is not None:
        return job
    if not _company_lookupable(job.company):
        return job
    html = fetch_glassdoor_company_html(job.company, user_agent=user_agent)
    if not html:
        log.debug("Glassdoor HTTP lookup failed for %r (often blocked)", job.company)
        return job
    if not html:
        return job
    rating, reviews = parse_glassdoor_from_page(html)
    updates: dict[str, object] = {}
    if rating is not None and job.glassdoor_rating is None:
        updates["glassdoor_rating"] = rating
    if reviews is not None and job.glassdoor_reviews is None:
        updates["glassdoor_reviews"] = reviews
    if not updates:
        return job
    return job.model_copy(update=updates)
