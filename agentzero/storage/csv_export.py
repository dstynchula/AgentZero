"""Export tracked jobs to CSV for sorting and filtering."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from agentzero.models import JobPosting
from agentzero.storage.db import Database


def match_tier(score: float | None) -> str:
    """Human-readable fit bucket for Sheets sorting."""
    if score is None:
        return ""
    if score >= 0.75:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


EXPORT_COLUMNS = [
    "source",
    "company",
    "title",
    "comp_min",
    "comp_max",
    "comp_is_estimate",
    "currency",
    "company_size",
    "glassdoor_rating",
    "glassdoor_reviews",
    "date_posted",
    "posting_age_days",
    "location",
    "remote",
    "url",
    "careers_url",
    "match_score",
    "match_rationale",
    "match_tier",
    "status",
    "date_first_contacted",
    "date_applied",
    "notes",
    "job_id",
]

# Operator-facing Google Sheet (CSV export keeps the full schema above).
SHEET_COLUMNS = [
    "source",
    "company",
    "title",
    "location",
    "comp_min",
    "comp_max",
    "glassdoor_rating",
    "match_score",
    "status",
    "date_applied",
    "notes",
    "url",
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
        "comp_is_estimate": job.comp_is_estimate,
        "currency": job.currency,
        "company_size": job.company_size,
        "glassdoor_rating": job.glassdoor_rating,
        "glassdoor_reviews": job.glassdoor_reviews,
        "date_posted": job.date_posted.isoformat() if job.date_posted else "",
        "posting_age_days": posting_age_days(job, today=today),
        "location": job.location,
        "remote": job.remote,
        "url": job.url,
        "careers_url": job.careers_url or "",
        "match_score": job.match_score,
        "match_rationale": job.match_rationale or "",
        "match_tier": match_tier(job.match_score),
        "status": job.status.value,
        "date_first_contacted": (
            job.date_first_contacted.isoformat() if job.date_first_contacted else ""
        ),
        "date_applied": job.date_applied.isoformat() if job.date_applied else "",
        "notes": job.notes or "",
        "job_id": job.job_id,
    }


def job_to_sheet_row(job: JobPosting, *, today: date | None = None) -> dict[str, object]:
    """Subset of ``job_to_row`` for the live Google Sheet tracker."""
    full = job_to_row(job, today=today)
    return {column: full[column] for column in SHEET_COLUMNS}


def export_csv(
    db: Database,
    path: Path | str,
    *,
    today: date | None = None,
    min_match_score: float | None = None,
) -> int:
    """Write jobs to ``path``; returns row count."""
    from agentzero.rank.export_filter import filter_jobs_for_export

    jobs, _ = filter_jobs_for_export(db.list_jobs(), min_match_score)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for job in jobs:
            writer.writerow(job_to_row(job, today=today))
    return len(jobs)
