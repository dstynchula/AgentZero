"""Write helpers for the operator web UI (no hard deletes)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentzero.apply.sheet_fields import parse_sheet_status
from agentzero.models import ApplicationStatus, JobPosting

if TYPE_CHECKING:
    from agentzero.storage.db import Database

MAX_NOTES_LENGTH = 8_192


class JobNotFoundError(LookupError):
    """Raised when a mutation targets a missing job_id."""


def update_job_status(db: Database, job_id: str, status: str | ApplicationStatus) -> JobPosting:
    """Persist a new application status for *job_id*."""
    job = db.get_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)

    if isinstance(status, ApplicationStatus):
        parsed = status
    else:
        parsed = parse_sheet_status(status)
        if parsed is None:
            raise ValueError(f"invalid status: {status!r}")

    updated = job.model_copy(update={"status": parsed})
    db.upsert_job(updated)
    return updated


def update_job_notes(db: Database, job_id: str, notes: str) -> JobPosting:
    """Update free-text notes for *job_id*."""
    job = db.get_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)

    text = notes.strip()
    if len(text) > MAX_NOTES_LENGTH:
        raise ValueError(f"notes exceed {MAX_NOTES_LENGTH} characters")

    updated = job.model_copy(update={"notes": text or None})
    db.upsert_job(updated)
    return updated


def reject_job(db: Database, job_id: str) -> JobPosting:
    """Soft-delete: mark *job_id* as rejected (kept for dedupe, hidden from default UI)."""
    job = db.get_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)

    if job.status == ApplicationStatus.REJECTED:
        return job

    updated = job.model_copy(update={"status": ApplicationStatus.REJECTED})
    db.upsert_job(updated)
    return updated
