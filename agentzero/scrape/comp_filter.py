"""Filter jobs by a minimum acceptable salary using the posted range's upper bound."""

from __future__ import annotations

from agentzero.models import JobPosting


def posted_comp_ceiling(job: JobPosting) -> float | None:
    """Return the top of the posted comp range (``comp_max``, else ``comp_min``)."""
    if job.comp_max is not None:
        return job.comp_max
    if job.comp_min is not None:
        return job.comp_min
    return None


def meets_salary_floor(job: JobPosting, floor: float | None) -> bool:
    """True when comp is unknown or the posted range reaches at least ``floor``."""
    if floor is None:
        return True
    ceiling = posted_comp_ceiling(job)
    if ceiling is None:
        return True
    return ceiling >= floor


def filter_by_salary_floor(
    jobs: list[JobPosting],
    floor: float | None,
) -> tuple[list[JobPosting], list[JobPosting]]:
    """Split jobs into kept vs rejected by ``meets_salary_floor``."""
    if floor is None:
        return jobs, []
    kept: list[JobPosting] = []
    rejected: list[JobPosting] = []
    for job in jobs:
        if meets_salary_floor(job, floor):
            kept.append(job)
        else:
            rejected.append(job)
    return kept, rejected
