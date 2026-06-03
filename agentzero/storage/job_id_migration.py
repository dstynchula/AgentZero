"""Re-key jobs whose stored ``job_id`` differs from ``JobPosting.job_id`` (stable hash)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentzero.models import ApplicationStatus, JobPosting

if TYPE_CHECKING:
    from agentzero.storage.db import Database


@dataclass(frozen=True, slots=True)
class StaleJobKey:
    stored_id: str
    canonical_id: str
    job: JobPosting


@dataclass
class JobIdMigrationResult:
    scanned: int = 0
    rekeyed: int = 0
    merged: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)


def find_stale_job_keys(db: Database) -> list[StaleJobKey]:
    """Return rows whose primary key does not match ``JobPosting.job_id``."""
    stale: list[StaleJobKey] = []
    for stored_id, job in db.iter_jobs_with_stored_ids():
        canonical_id = job.job_id
        if stored_id != canonical_id:
            stale.append(StaleJobKey(stored_id, canonical_id, job))
    return stale


def _merge_tracker_fields(primary: JobPosting, secondary: JobPosting) -> JobPosting:
    """Merge operator tracker fields when two rows share one canonical listing."""
    notes_a = (primary.notes or "").strip()
    notes_b = (secondary.notes or "").strip()
    if notes_a and notes_b and notes_b not in notes_a:
        notes = f"{notes_a}\n{notes_b}" if notes_a else notes_b
    else:
        notes = notes_a or notes_b or None

    status = primary.status
    if secondary.status not in (ApplicationStatus.NEW, ApplicationStatus.LEAD):
        if status in (ApplicationStatus.NEW, ApplicationStatus.LEAD):
            status = secondary.status

    return primary.model_copy(
        update={
            "status": status,
            "date_applied": primary.date_applied or secondary.date_applied,
            "date_first_contacted": primary.date_first_contacted
            or secondary.date_first_contacted,
            "notes": notes,
        }
    )


def migrate_stale_job_ids(db: Database, *, dry_run: bool = False) -> JobIdMigrationResult:
    """Re-key stale rows to canonical ``JobPosting.job_id`` values."""
    result = JobIdMigrationResult()
    stale = find_stale_job_keys(db)
    result.scanned = len(stale)

    for entry in stale:
        canonical_id = entry.canonical_id
        if db.get_job_by_stored_id(canonical_id) is not None:
            if dry_run:
                result.merged += 1
                result.details.append(
                    f"merge {entry.stored_id} -> {canonical_id} "
                    f"({entry.job.company} / {entry.job.title})"
                )
                continue
            existing = db.get_job_by_stored_id(canonical_id)
            assert existing is not None
            merged = _merge_tracker_fields(existing, entry.job)
            db.upsert_job(merged)
            db.delete_jobs([entry.stored_id])
            result.merged += 1
            result.details.append(
                f"merged {entry.stored_id} into {canonical_id} "
                f"({entry.job.company} / {entry.job.title})"
            )
            continue

        if dry_run:
            result.rekeyed += 1
            result.details.append(
                f"rekey {entry.stored_id} -> {canonical_id} "
                f"({entry.job.company} / {entry.job.title})"
            )
            continue

        if db.rekey_job(entry.stored_id, canonical_id, entry.job):
            result.rekeyed += 1
            result.details.append(
                f"rekeyed {entry.stored_id} -> {canonical_id} "
                f"({entry.job.company} / {entry.job.title})"
            )
        else:
            result.skipped += 1
            result.details.append(f"skipped {entry.stored_id} (missing row)")

    return result
