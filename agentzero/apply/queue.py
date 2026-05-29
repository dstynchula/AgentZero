"""Human-in-the-loop application queue (never auto-submits)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agentzero.models import ApplicationStatus, JobPosting
from agentzero.storage.db import Database


@dataclass(frozen=True, slots=True)
class QueuedApplication:
    job: JobPosting
    prefill: dict[str, str]


class ApplicationQueue:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_pending(self) -> list[QueuedApplication]:
        pending_ids = self._db.list_pending("draft_status")
        items: list[QueuedApplication] = []
        for job_id in pending_ids:
            job = self._db.get_job(job_id)
            if job is None:
                continue
            if job.status in {ApplicationStatus.APPLIED, ApplicationStatus.REJECTED}:
                continue
            items.append(QueuedApplication(job=job, prefill=build_prefill(job)))
        return items

    def mark_contacted(self, job_id: str, *, contacted: date | None = None) -> None:
        job = self._require_job(job_id)
        when = contacted or date.today()
        updated = job.model_copy(
            update={
                "status": ApplicationStatus.CONTACTED,
                "date_first_contacted": when,
            }
        )
        self._db.upsert_job(updated)

    def mark_applied(self, job_id: str, *, applied: date | None = None) -> None:
        job = self._require_job(job_id)
        if job.status == ApplicationStatus.APPLIED:
            return
        when = applied or date.today()
        contacted = job.date_first_contacted or when
        updated = job.model_copy(
            update={
                "status": ApplicationStatus.APPLIED,
                "date_first_contacted": contacted,
                "date_applied": when,
            }
        )
        self._db.upsert_job(updated)
        self._db.mark_pipeline(job_id, "draft_status", "done")

    def _require_job(self, job_id: str) -> JobPosting:
        job = self._db.get_job(job_id)
        if job is None:
            raise KeyError(f"Unknown job_id: {job_id}")
        return job


def build_prefill(job: JobPosting) -> dict[str, str]:
    return {
        "company": job.company,
        "role": job.title,
        "job_url": job.url,
        "source": job.source,
    }
