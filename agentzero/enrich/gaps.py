"""Detect missing enrichment fields on stored jobs."""

from __future__ import annotations

from agentzero.enrich.careers_urls import is_low_quality_careers_url
from agentzero.models import JobPosting


def enrichment_gaps(job: JobPosting) -> list[str]:
    """Return human-readable names of fields still missing."""
    gaps: list[str] = []
    if not job.description:
        gaps.append("description")
    if job.comp_min is None and job.comp_max is None:
        gaps.append("comp")
    if not job.company_size:
        gaps.append("company_size")
    if job.glassdoor_rating is None:
        gaps.append("glassdoor_rating")
    if job.glassdoor_reviews is None:
        gaps.append("glassdoor_reviews")
    if not job.careers_url or is_low_quality_careers_url(job.careers_url, job.company):
        gaps.append("careers_url")
    return gaps


def needs_detail_fetch(job: JobPosting) -> bool:
    missing_description = not job.description
    missing_comp = job.comp_min is None and job.comp_max is None
    return missing_description or missing_comp


def needs_enrichment_pass(job: JobPosting) -> bool:
    return bool(enrichment_gaps(job))
