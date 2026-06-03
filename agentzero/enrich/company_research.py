"""Company-level web research: size, Glassdoor, careers URLs."""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentzero.enrich.careers_urls import (
    extract_careers_urls,
    is_low_quality_careers_url,
    pick_verified_careers_url,
)
from agentzero.enrich.company_website import pick_company_website
from agentzero.enrich.snippet_parse import (
    parse_company_size_from_text,
    parse_glassdoor_from_text,
    parse_public_company_from_text,
    snippet_mentions_company,
)
from agentzero.enrich.web_search import SearchHit, search_web
from agentzero.models import JobPosting
from agentzero.net.http_client import safe_get_text
from agentzero.net.url_safety import url_host_matches
from agentzero.scrape.glassdoor import parse_glassdoor_company_html
from agentzero.scrape.resilience import DEFAULT_USER_AGENT

if TYPE_CHECKING:
    from agentzero.config import Settings

log = logging.getLogger(__name__)


@dataclass
class CompanyWebFacts:
    company_size: str | None = None
    glassdoor_rating: float | None = None
    glassdoor_reviews: int | None = None
    careers_urls: list[str] = field(default_factory=list)
    company_website: str | None = None
    is_public_company: bool | None = None
    stock_ticker: str | None = None


def _company_key(company: str) -> str:
    return re.sub(r"\s+", " ", company.strip().lower())


def _collect_snippet_text(hits: list[SearchHit]) -> str:
    return "\n".join(hit.title for hit in hits) + "\n" + "\n".join(
        hit.snippet for hit in hits
    )


def _merge_glassdoor(
    facts: CompanyWebFacts, rating: float | None, reviews: int | None
) -> None:
    if rating is not None and facts.glassdoor_rating is None:
        facts.glassdoor_rating = rating
    if reviews is not None and facts.glassdoor_reviews is None:
        facts.glassdoor_reviews = reviews


def _merge_size(facts: CompanyWebFacts, size: str | None) -> None:
    if size and not facts.company_size:
        facts.company_size = size


def _merge_public_company(
    facts: CompanyWebFacts,
    is_public: bool | None,
    ticker: str | None,
) -> None:
    if is_public is not None and facts.is_public_company is None:
        facts.is_public_company = is_public
    if ticker and not facts.stock_ticker:
        facts.stock_ticker = ticker


def _merge_company_website(facts: CompanyWebFacts, url: str | None) -> None:
    if url and not facts.company_website:
        facts.company_website = url


def _fetch_glassdoor_page(url: str, *, user_agent: str) -> tuple[float | None, int | None]:
    html = safe_get_text(url, user_agent=user_agent, max_chars=50_000)
    if not html:
        return None, None
    rating, reviews = parse_glassdoor_company_html(html)
    if rating is None:
        rating, reviews = parse_glassdoor_from_text(html)
    return rating, reviews


def _parse_hits_for_facts(
    hits: list[SearchHit],
    facts: CompanyWebFacts,
    *,
    company: str,
    user_agent: str,
) -> None:
    blob = _collect_snippet_text(hits)
    _merge_size(facts, parse_company_size_from_text(blob))
    rating, reviews = parse_glassdoor_from_text(blob)
    _merge_glassdoor(facts, rating, reviews)
    for hit in hits:
        hit_text = f"{hit.title}\n{hit.snippet}"
        if snippet_mentions_company(hit_text, company):
            is_public, ticker = parse_public_company_from_text(hit_text, company=company)
            _merge_public_company(facts, is_public, ticker)
    _merge_company_website(facts, pick_company_website(hits, company=company))

    for hit in hits:
        if url_host_matches(hit.url, "glassdoor.com"):
            rating, reviews = parse_glassdoor_from_text(f"{hit.title}\n{hit.snippet}")
            _merge_glassdoor(facts, rating, reviews)
            if facts.glassdoor_rating is None or facts.glassdoor_reviews is None:
                page_rating, page_reviews = _fetch_glassdoor_page(
                    hit.url, user_agent=user_agent
                )
                _merge_glassdoor(facts, page_rating, page_reviews)
        for url in extract_careers_urls([hit], company=company):
            if url not in facts.careers_urls:
                facts.careers_urls.append(url)


def _facts_incomplete(facts: CompanyWebFacts) -> bool:
    return (
        facts.company_size is None
        or facts.glassdoor_rating is None
        or facts.glassdoor_reviews is None
        or facts.company_website is None
        or facts.is_public_company is None
    )


def research_company(
    company: str,
    *,
    settings: Settings,
    user_agent: str | None = None,
) -> CompanyWebFacts:
    ua = user_agent or settings.scrape_user_agent or DEFAULT_USER_AGENT
    max_results = settings.enrich_web_search_max_results
    delay = settings.enrich_web_search_delay_seconds
    facts = CompanyWebFacts()

    queries = [
        f"{company} glassdoor reviews rating",
        f"{company} number of employees company size linkedin",
        f"{company} careers jobs site",
        f"{company} official website",
        f"{company} stock ticker publicly traded NASDAQ NYSE",
    ]
    for index, query in enumerate(queries):
        hits = search_web(
            query,
            max_results=max_results,
            user_agent=ua,
            delay_seconds=delay if index > 0 else 0.0,
        )
        _parse_hits_for_facts(hits, facts, company=company, user_agent=ua)

    if _facts_incomplete(facts):
        for index, query in enumerate(
            [
                f"site:glassdoor.com {company} reviews",
                f"{company} employees linkedin company profile",
            ]
        ):
            hits = search_web(
                query,
                max_results=max_results,
                user_agent=ua,
                delay_seconds=delay if index > 0 else 0.0,
            )
            _parse_hits_for_facts(hits, facts, company=company, user_agent=ua)

    return facts


class CompanyFactsCache:
    """Thread-safe cache of per-company web research (one search per employer per batch)."""

    def __init__(self) -> None:
        self._data: dict[str, CompanyWebFacts] = {}
        self._lock = threading.Lock()

    def get(
        self,
        company: str,
        *,
        settings: Settings,
        user_agent: str | None = None,
    ) -> CompanyWebFacts:
        key = _company_key(company)
        with self._lock:
            if key in self._data:
                return self._data[key]
            facts = research_company(company, settings=settings, user_agent=user_agent)
            self._data[key] = facts
            return facts


def enrich_job_web_research(
    job: JobPosting,
    *,
    settings: Settings,
    cache: CompanyFactsCache | dict[str, CompanyWebFacts] | None = None,
    user_agent: str | None = None,
) -> JobPosting:
    ua = user_agent or settings.scrape_user_agent or DEFAULT_USER_AGENT

    if isinstance(cache, CompanyFactsCache):
        facts = cache.get(job.company, settings=settings, user_agent=ua)
    elif isinstance(cache, dict):
        key = _company_key(job.company)
        if key not in cache:
            cache[key] = research_company(job.company, settings=settings, user_agent=ua)
            if settings.enrich_web_search_delay_seconds > 0:
                time.sleep(settings.enrich_web_search_delay_seconds)
        facts = cache[key]
    else:
        facts = research_company(job.company, settings=settings, user_agent=ua)

    updates: dict[str, object] = {}
    if not job.company_size and facts.company_size:
        updates["company_size"] = facts.company_size
    if job.glassdoor_rating is None and facts.glassdoor_rating is not None:
        updates["glassdoor_rating"] = facts.glassdoor_rating
    if job.glassdoor_reviews is None and facts.glassdoor_reviews is not None:
        updates["glassdoor_reviews"] = facts.glassdoor_reviews

    careers_missing = not job.careers_url or is_low_quality_careers_url(
        job.careers_url, job.company
    )
    if careers_missing and facts.careers_urls:
        verified = pick_verified_careers_url(
            job.company, job.title, facts.careers_urls, user_agent=ua
        )
        if verified:
            updates["careers_url"] = verified
    if not job.company_website and facts.company_website:
        updates["company_website"] = facts.company_website
    if facts.stock_ticker:
        updates["stock_ticker"] = facts.stock_ticker
        updates["is_public_company"] = True
    elif facts.is_public_company is False:
        updates["is_public_company"] = False
        updates["stock_ticker"] = None
    elif facts.is_public_company is True:
        updates["is_public_company"] = True
    elif job.is_public_company is not None or job.stock_ticker:
        updates["is_public_company"] = None
        updates["stock_ticker"] = None

    if not updates:
        return job
    return job.model_copy(update=updates)
