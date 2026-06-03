"""Write helpers for the operator web UI (no hard deletes)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentzero.apply.tracker_fields import parse_tracker_status
from agentzero.enrich.pipeline import enrich_job, enrich_job_deep
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.storage.csv_export import job_to_row

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.ingest.resume import ResumeProfile
    from agentzero.llm.provider import LLMProvider
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
        parsed = parse_tracker_status(status)
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


def enrich_job_record(
    db: Database,
    job_id: str,
    *,
    settings: Settings,
    llm: LLMProvider | None = None,
    profile: ResumeProfile | None = None,
    rank: bool = True,
) -> JobPosting:
    """Run deep enrich (and optional rank) for a single job."""
    job = db.get_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)

    updated = enrich_job_deep(
        job,
        settings=settings,
        fetch_detail=settings.enrich_fetch_details,
        glassdoor_lookup=settings.enrich_glassdoor_lookup,
        web_search=settings.enrich_web_search,
        allow_browser=True,
    )
    updated = enrich_job(updated, settings=settings)

    if rank and profile is not None and llm is not None:
        from agentzero.rank.matcher import rank_job

        match = rank_job(
            updated,
            profile,
            llm=llm,
            max_description_chars=settings.rank_description_max_chars,
        )
        updated = updated.model_copy(
            update={
                "match_score": match.match_score,
                "match_rationale": match.rationale,
            }
        )
        db.mark_pipeline(job_id, "rank_status", "done")

    db.upsert_job(updated)
    db.mark_pipeline(job_id, "enrich_status", "done")
    return updated


def enrich_job_record_payload(job: JobPosting) -> dict[str, object]:
    """JSON-friendly job payload after enrich."""
    row = job_to_row(job)
    row["description"] = job.description or ""
    return row
