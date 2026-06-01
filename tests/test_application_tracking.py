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

def test_is_applied_by_status_only():
    job = _job(status=ApplicationStatus.APPLIED)
    assert is_applied(job)
    assert not is_applied(_job(status=ApplicationStatus.NEW))


def test_offer_status_is_application_locked():
    assert is_application_locked(_job(status=ApplicationStatus.OFFER))


def test_list_applied_jobs(tmp_path):
    db = Database(tmp_path / "jobs.db")
    applied = _job(url="https://x.com/a", date_applied=date(2026, 5, 1))
    pending = _job(url="https://x.com/b", status=ApplicationStatus.NEW)
    db.upsert_job(applied)
    db.upsert_job(pending)
    from agentzero.apply.tracking import list_applied_jobs

    assert len(list_applied_jobs(db)) == 1


def test_find_job_by_job_id_and_company_title(tmp_path):
    db = Database(tmp_path / "jobs.db")
    job = _job(url="https://x.com/job", company="Acme Corp", title="Staff Engineer")
    db.upsert_job(job)
    by_id = find_job_for_tracker_row(db, {"job_id": job.job_id})
    by_title = find_job_for_tracker_row(
        db,
        {"company": "  acme corp ", "title": "staff engineer"},
    )
    assert by_id is not None
    assert by_title is not None
    assert by_id.job_id == job.job_id


def test_job_from_tracker_row_placeholder_url_and_fields():
    job = job_from_tracker_row(
        {
            "company": "Acme",
            "title": "Security Engineer",
            "url": "not-a-url",
            "source": "tracker",
            "remote": "yes",
            "comp_min": "$120,000",
            "comp_max": "bad",
            "match_score": "2.5",
            "glassdoor_reviews": "1,234",
            "location": "Remote",
            "notes": "applied via referral",
        }
    )
    assert job is not None
    assert job.url.startswith("https://applied.local/tracker/")
    assert job.remote is True
    assert job.comp_min == 120_000.0
    assert job.comp_max is None
    assert job.match_score == 1.0
    assert job.glassdoor_reviews == 1234
    assert job.notes == "applied via referral"


def test_job_from_tracker_row_status_from_date_applied():
    job = job_from_tracker_row(
        {
            "company": "Acme",
            "title": "Security Engineer",
            "url": "https://x.com/1",
            "date_applied": "2026-05-01",
        }
    )
    assert job is not None
    assert job.status == ApplicationStatus.APPLIED
    assert job.date_applied == date(2026, 5, 1)


def test_import_skips_rows_without_identity(tmp_path):
    db = Database(tmp_path / "jobs.db")
    result = import_tracker_rows(db, [{"notes": "orphan"}])
    assert result.skipped == 1
    assert result.created == 0


def test_import_skips_untracked_new_rows(tmp_path):
    db = Database(tmp_path / "jobs.db")
    row = {
        "company": "Acme",
        "title": "Engineer",
        "url": "https://x.com/new",
    }
    result = import_tracker_rows(db, [row])
    assert result.skipped == 1
    assert db.count_jobs() == 0


def test_import_skips_title_mismatch_without_applied_date(tmp_path):
    db = Database(tmp_path / "jobs.db")
    row = {
        "company": "Acme",
        "title": "Marketing Manager",
        "url": "https://x.com/m",
        "status": "reviewed",
    }
    result = import_tracker_rows(db, [row], search_terms=["security engineer"])
    assert result.skipped == 1


def test_import_dry_run_update_path(tmp_path):
    db = Database(tmp_path / "jobs.db")
    job = _job(url="https://x.com/existing")
    db.upsert_job(job)
    row = {
        "company": job.company,
        "title": job.title,
        "url": job.url,
        "notes": "updated in sheet",
    }
    preview = import_tracker_rows(db, [row], dry_run=True)
    assert preview.updated == 1
    assert db.get_job(job.job_id).notes is None


def test_parse_sheet_row_and_rows_from_values():
    from agentzero.apply.tracking import parse_sheet_row, rows_from_sheet_values

    row = parse_sheet_row(["company", "title"], ["Acme", "Eng"])
    assert row == {"company": "Acme", "title": "Eng"}

    rows = rows_from_sheet_values(
        [
            ["company", "title"],
            ["Acme", "Eng"],
            ["", ""],
        ]
    )
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"


def test_tracker_rows_with_applications():
    from agentzero.apply.tracking import tracker_rows_with_applications

    rows = tracker_rows_with_applications(
        [
            {"company": "A", "date_applied": "2026-05-01"},
            {"company": "B", "status": "offer"},
            {"company": "C", "status": "new"},
        ]
    )
    assert len(rows) == 2
