"""Company size enrichment."""

from __future__ import annotations

from agentzero.enrich.comp import parse_employee_count
from agentzero.models import JobPosting

SIZE_BUCKETS = (
    (10, "1-10"),
    (50, "11-50"),
    (200, "51-200"),
    (500, "201-500"),
    (1000, "501-1000"),
    (5000, "1001-5000"),
)


def bucket_employee_count(count: int) -> str:
    for limit, label in SIZE_BUCKETS:
        if count <= limit:
            return label
    return "5000+"


def enrich_company_size(job: JobPosting) -> JobPosting:
    if job.company_size:
        return job
    text = job.description or ""
    count = parse_employee_count(text)
    if count is None:
        return job
    return job.model_copy(update={"company_size": bucket_employee_count(count)})
