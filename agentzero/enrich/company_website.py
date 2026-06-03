"""Discover corporate homepage URLs from web search hits."""

from __future__ import annotations

import re

from agentzero.enrich.careers_urls import SKIP_URL_RE, _company_slug
from agentzero.enrich.web_search import SearchHit
from agentzero.net.url_safety import UnsafeURLError, validate_fetch_url

CAREERS_PATH_RE = re.compile(
    r"/(careers|jobs|join|hiring|openings)(/|$)",
    re.IGNORECASE,
)


def is_job_board_or_aggregator(url: str) -> bool:
    return bool(SKIP_URL_RE.search(url))


def score_company_website(url: str, company: str) -> int:
    if is_job_board_or_aggregator(url):
        return -100
    if CAREERS_PATH_RE.search(url):
        return -20
    lowered = url.lower()
    score = 0
    slug = _company_slug(company)
    if slug and slug in lowered.replace("-", "").replace(".", "").replace("/", ""):
        score += 5
    if lowered.startswith("https://www.") or lowered.startswith("http://www."):
        score += 1
    if lowered.count("/") <= 3:
        score += 1
    return score


def pick_company_website(hits: list[SearchHit], *, company: str) -> str | None:
    """Return the best corporate homepage URL, or None when uncertain."""
    best_url: str | None = None
    best_score = 0
    for hit in hits:
        url = hit.url.strip()
        if not url or is_job_board_or_aggregator(url):
            continue
        try:
            validate_fetch_url(url)
        except UnsafeURLError:
            continue
        score = score_company_website(url, company)
        if score > best_score:
            best_score = score
            best_url = url
    if best_score < 3:
        return None
    return best_url
