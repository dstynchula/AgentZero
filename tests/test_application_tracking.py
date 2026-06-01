"""Tests for application tracking import and protection."""

from __future__ import annotations

from datetime import date

from agentzero.apply.tracking import (
    find_job_for_tracker_row,
    import_tracker_rows,
    is_application_locked,
    is_applied,
    job_from_tracker_row,
)
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.scrape.remote_policy import job_is_remote
from agentzero.storage.db import Database


def _job(**kwargs) -> JobPosting:
    base = dict(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    base.update(kwargs)
    return JobPosting(**base)


def test_is_applied_and_locked():
    applied = _job(date_applied=date(2026, 5, 1), status=ApplicationStatus.NEW)
    assert is_applied(applied)
    assert is_application_locked(applied)


def test_rejected_lead_locked_for_prune_not_sheet_export():
    from agentzero.rank.export_filter import job_included_in_export

    rejected = _job(status=ApplicationStatus.REJECTED, match_score=0.95)
    assert is_application_locked(rejected)
    assert not job_included_in_export(rejected, 0.75)


def test_job_is_remote_united_states():
    assert job_is_remote(_job(location="United States"))
    assert job_is_remote(_job(location="TX"))
    assert not job_is_remote(_job(location="Woodland Hills, CA"))


def test_applied_job_protected_from_remote_purge():
    job = _job(location="San Francisco, CA", date_applied=date(2026, 5, 1))
    assert job_is_remote(job)


def test_import_creates_restored_application(tmp_path):
    db = Database(tmp_path / "jobs.db")
    row = {
        "company": "Cohere",
        "title": "Senior Security Engineer",
        "url": "https://jobs.example/cohere",
        "source": "linkedin",
        "location": "San Francisco, CA",
        "date_applied": "2026-05-29",
        "status": "applied",
    }
    result = import_tracker_rows(db, [row])
    assert result.created == 1
    job = find_job_for_tracker_row(db, row)
    assert job is not None
    assert is_applied(job)
    assert job.date_applied == date(2026, 5, 29)


def test_import_updates_existing_by_url(tmp_path):
    db = Database(tmp_path / "jobs.db")
    job = _job(url="https://jobs.example/cohere", company="Cohere")
    db.upsert_job(job)
    row = {
        "company": "Cohere",
        "title": "Senior Security Engineer",
        "url": "https://jobs.example/cohere",
        "date_applied": "2026-05-29",
    }
    result = import_tracker_rows(db, [row])
    assert result.updated == 1
    stored = db.get_job(job.job_id)
    assert stored is not None
    assert stored.date_applied == date(2026, 5, 29)


def test_job_from_tracker_row_requires_company_title():
    assert job_from_tracker_row({"date_applied": "2026-05-01"}) is None


def test_dry_run_reports_counts_without_writing(tmp_path):
    db = Database(tmp_path / "jobs.db")
    row = {
        "company": "Cohere",
        "title": "Senior Security Engineer",
        "url": "https://jobs.example/cohere",
        "source": "linkedin",
        "date_applied": "2026-05-29",
        "status": "applied",
    }
    preview = import_tracker_rows(db, [row], dry_run=True)
    assert preview.created == 1
    assert db.count_jobs() == 0

    result = import_tracker_rows(db, [row])
    assert result.created == 1
    assert db.count_jobs() == 1


def test_duplicate_rows_create_one_job(tmp_path):
    db = Database(tmp_path / "jobs.db")
    row = {
        "company": "Cohere",
        "title": "Senior Security Engineer",
        "url": "https://jobs.example/cohere",
        "source": "linkedin",
        "date_applied": "2026-05-29",
    }
    result = import_tracker_rows(db, [dict(row), dict(row)])
    assert result.created == 1
    assert db.count_jobs() == 1


def test_match_score_from_sheet_is_clamped():
    job = job_from_tracker_row(
        {
            "company": "Acme",
            "title": "Security Engineer",
            "url": "https://x.com/1",
            "match_score": "999",
        }
    )
    assert job is not None
    assert job.match_score == 1.0
