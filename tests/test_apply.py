from datetime import date

from agentzero.apply.queue import ApplicationQueue, build_prefill
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.storage.db import Database


def test_build_prefill():
    job = JobPosting(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    prefill = build_prefill(job)
    assert prefill["company"] == "Acme"
    assert prefill["role"] == "Eng"


def test_application_queue_and_dates(tmp_path):
    db = Database(tmp_path / "jobs.db")
    job = JobPosting(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    db.upsert_job(job)
    db.mark_pipeline(job.job_id, "draft_status", "pending")
    queue = ApplicationQueue(db)
    pending = queue.list_pending()
    assert len(pending) == 1
    assert pending[0].prefill["job_url"] == job.url

    queue.mark_contacted(job.job_id, contacted=date(2026, 5, 1))
    stored = db.get_job(job.job_id)
    assert stored is not None
    assert stored.status == ApplicationStatus.CONTACTED
    assert stored.date_first_contacted == date(2026, 5, 1)

    queue.mark_applied(job.job_id, applied=date(2026, 5, 5))
    stored = db.get_job(job.job_id)
    assert stored.status == ApplicationStatus.APPLIED
    assert stored.date_applied == date(2026, 5, 5)

    queue.mark_applied(job.job_id)
    db.close()


def test_mark_applied_is_idempotent(tmp_path):
    db = Database(tmp_path / "jobs.db")
    job = JobPosting(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    db.upsert_job(job)
    queue = ApplicationQueue(db)
    queue.mark_applied(job.job_id)
    first = db.get_job(job.job_id).date_applied
    queue.mark_applied(job.job_id)
    assert db.get_job(job.job_id).date_applied == first
    db.close()
