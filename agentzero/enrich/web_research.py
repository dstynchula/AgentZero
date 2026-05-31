"""Web research enrichment — re-exports for backward compatibility."""

from agentzero.enrich.careers_urls import (
    extract_careers_urls,
    fetch_page_text,
    is_low_quality_careers_url,
    pick_verified_careers_url,
    score_careers_url,
    title_keywords,
)
from agentzero.enrich.company_research import (
    CompanyFactsCache,
    CompanyWebFacts,
    enrich_job_web_research,
    research_company,
)

__all__ = [
    "CompanyFactsCache",
    "CompanyWebFacts",
    "enrich_job_web_research",
    "extract_careers_urls",
    "fetch_page_text",
    "is_low_quality_careers_url",
    "pick_verified_careers_url",
    "research_company",
    "score_careers_url",
    "title_keywords",
]
