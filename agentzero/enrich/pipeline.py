"""Run all enrichment steps on a job posting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentzero.enrich.careers_urls import is_low_quality_careers_url
from agentzero.enrich.comp import enrich_comp
from agentzero.enrich.company import enrich_company_size
from agentzero.enrich.detail_fetch import fetch_and_merge_detail
from agentzero.enrich.gaps import needs_detail_fetch
from agentzero.enrich.glassdoor_company import enrich_glassdoor_company
from agentzero.enrich.glassdoor_rating import enrich_glassdoor
from agentzero.enrich.web_research import CompanyFactsCache, enrich_job_web_research
from agentzero.models import JobPosting
from agentzero.scrape.resilience import DEFAULT_USER_AGENT

if TYPE_CHECKING:
    from agentzero.config import Settings


def _needs_company_web_facts(job: JobPosting) -> bool:
    careers_gap = not job.careers_url or is_low_quality_careers_url(
        job.careers_url, job.company
    )
    return (
        not job.company_size
        or job.glassdoor_rating is None
        or job.glassdoor_reviews is None
        or careers_gap
        or not job.company_website
        or job.is_public_company is None
    )


def enrich_job(job: JobPosting, *, settings: Settings | None = None) -> JobPosting:
    """Parse comp / size / rating from fields on the job; optional web research."""
    from agentzero.config import get_settings

    job = enrich_comp(job)
    job = enrich_company_size(job)
    job = enrich_glassdoor(job)
    cfg = settings or get_settings()
    if cfg.enrich_web_search and _needs_company_web_facts(job):
        job = enrich_job_web_research(job, settings=cfg)
    return job


def enrich_job_deep(
    job: JobPosting,
    *,
    settings: Settings | None = None,
    fetch_detail: bool = True,
    glassdoor_lookup: bool = True,
    web_search: bool = True,
    allow_browser: bool = True,
    company_cache: CompanyFactsCache | None = None,
) -> JobPosting:
    """Secondary pass: fetch posting + company pages, then parse enrichment fields."""
    from agentzero.config import get_settings

    cfg = settings or get_settings()
    ua = cfg.scrape_user_agent or DEFAULT_USER_AGENT

    if fetch_detail and needs_detail_fetch(job):
        job = fetch_and_merge_detail(job, settings=cfg, allow_browser=allow_browser)

    job = enrich_job(job)

    if glassdoor_lookup and (
        job.glassdoor_rating is None or job.glassdoor_reviews is None
    ):
        job = enrich_glassdoor_company(job, user_agent=ua)

    needs_web = _needs_company_web_facts(job)
    if web_search and cfg.enrich_web_search and needs_web:
        job = enrich_job_web_research(
            job,
            settings=cfg,
            cache=company_cache,
            user_agent=ua,
        )

    return job
