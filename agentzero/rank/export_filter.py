"""Filter jobs before CSV export based on LLM match score."""

from __future__ import annotations

from agentzero.models import ApplicationStatus, JobPosting

# Lead-session statuses kept in SQLite for dedupe but omitted from CSV export.
_EXPORT_EXCLUDED_STATUSES = frozenset(
    {
        ApplicationStatus.LEAD,
        ApplicationStatus.REJECTED,
    }
)

# Applied tracker rows always export even when match_score is below the floor.
_ALWAYS_EXPORT_STATUSES = frozenset(
    {
        ApplicationStatus.APPLIED,
        ApplicationStatus.INTERVIEWING,
        ApplicationStatus.OFFER,
    }
)


def job_included_in_export(job: JobPosting, min_score: float | None) -> bool:
    """True when *job* should appear in CSV export.

    Unapproved or rejected leads stay in the DB only. Applied jobs always export.
    Unranked jobs export until scored. When ``min_score`` is set, ranked jobs
    below the floor are omitted.
    """
    if job.status in _EXPORT_EXCLUDED_STATUSES:
        return False
    if min_score is None or min_score <= 0:
        return True
    if job.date_applied is not None or job.status in _ALWAYS_EXPORT_STATUSES:
        return True
    if job.match_score is None:
        return True
    return job.match_score >= min_score


def filter_jobs_for_export(
    jobs: list[JobPosting],
    min_score: float | None,
) -> tuple[list[JobPosting], list[JobPosting]]:
    """Split jobs into exportable vs excluded (score floor or lead-session status)."""
    kept: list[JobPosting] = []
    excluded: list[JobPosting] = []
    for job in jobs:
        if job_included_in_export(job, min_score):
            kept.append(job)
        else:
            excluded.append(job)
    return kept, excluded
