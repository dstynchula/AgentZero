"""Run all enrichment steps on a job posting."""

from __future__ import annotations

from agentzero.enrich.comp import enrich_comp
from agentzero.enrich.company import enrich_company_size
from agentzero.enrich.glassdoor_rating import enrich_glassdoor
from agentzero.models import JobPosting


def enrich_job(job: JobPosting) -> JobPosting:
    job = enrich_comp(job)
    job = enrich_company_size(job)
    job = enrich_glassdoor(job)
    return job
