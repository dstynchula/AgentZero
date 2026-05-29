"""Export tracked jobs to CSV for sorting and filtering."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from agentzero.models import JobPosting
from agentzero.storage.db import Database

EXPORT_COLUMNS = [
    "source",
    "company",
    "title",
    "comp_min",
    "comp_max",
    "currency",
    "company_size",
    "glassdoor_rating",
    "glassdoor_reviews",
    "date_posted",
    "posting_age_days",
    "location",
    "remote",
    "url",
    "match_score",
    "status",
    "date_first_contacted",
    "date_applied",
    "notes",
    "job_id",
]


def posting_age_days(job: JobPosting, *, today: date | None = None) -> int | None:
    if job.date_posted is None:
        return None
    ref = today or date.today()
    posted = job.date_posted
    if isinstance(posted, datetime):
        posted = posted.date()
    return (ref - posted).days


def job_to_row(job: JobPosting, *, today: date | None = None) -> dict[str, object]:
    return {
        "source": job.source,
        "company": job.company,
        "title": job.title,
        "comp_min": job.comp_min,
        "comp_max": job.comp_max,
        "currency": job.currency,
        "company_size": job.company_size,
        "glassdoor_rating": job.glassdoor_rating,
        "glassdoor_reviews": job.glassdoor_reviews,
        "date_posted": job.date_posted.isoformat() if job.date_posted else "",
        "posting_age_days": posting_age_days(job, today=today),
        "location": job.location,
        "remote": job.remote,
        "url": job.url,
        "match_score": job.match_score,
        "status": job.status.value,
        "date_first_contacted": (
            job.date_first_contacted.isoformat() if job.date_first_contacted else ""
        ),
        "date_applied": job.date_applied.isoformat() if job.date_applied else "",
        "notes": job.notes or "",
        "job_id": job.job_id,
    }


def export_csv(db: Database, path: Path | str, *, today: date | None = None) -> int:
    """Write all jobs to ``path``; returns row count."""
    jobs = db.list_jobs()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for job in jobs:
            writer.writerow(job_to_row(job, today=today))
    return len(jobs)
