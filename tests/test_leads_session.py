"""Tests for lead-gathering session and LEAD status lifecycle."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from agentzero.apply.sheet_fields import merge_user_fields_from_sheet
from agentzero.ingest.search_profile import ResumeSearchProfile
from agentzero.leads.session import SearchTargets, approve_leads, list_pending_leads, reject_leads
from agentzero.loops.pipeline import Pipeline
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.rank.export_filter import job_included_in_export
from agentzero.storage.db import Database


def _job(**kwargs) -> JobPosting:
    base = dict(title="Security Engineer", company="Acme", url="https://x.com/1", source="indeed")
    base.update(kwargs)
    return JobPosting(**base)


def test_lead_excluded_from_export():
    lead = _job(status=ApplicationStatus.LEAD, match_score=0.95)
    assert not job_included_in_export(lead, 0.75)
    assert not job_included_in_export(lead, None)


def test_approved_new_included_in_export():
    active = _job(status=ApplicationStatus.NEW, match_score=0.9)
    assert job_included_in_export(active, 0.75)


def test_date_applied_promotes_reviewed_status():
    job = _job(status=ApplicationStatus.REVIEWED)
    merged, changed = merge_user_fields_from_sheet(job, {"date_applied": "2026-05-01"})
    assert changed
    assert merged.status == ApplicationStatus.APPLIED
    assert merged.date_applied == date(2026, 5, 1)


def test_date_applied_does_not_downgrade_offer():
    job = _job(status=ApplicationStatus.OFFER)
    merged, changed = merge_user_fields_from_sheet(job, {"date_applied": "2026-05-01"})
    assert changed
    assert merged.status == ApplicationStatus.OFFER


def test_date_applied_promotes_lead_status():
    job = _job(status=ApplicationStatus.LEAD)
    merged, changed = merge_user_fields_from_sheet(job, {"date_applied": "2026-05-01"})
    assert changed
    assert merged.status == ApplicationStatus.APPLIED


def test_pipeline_merge_preserves_applied_on_rescrape():
    existing = _job(status=ApplicationStatus.APPLIED, date_applied=date(2026, 5, 1))
    fresh = _job(location="Remote")
    merged = Pipeline._merge_scrape_job(existing, fresh, new_status=ApplicationStatus.LEAD)
    assert merged.status == ApplicationStatus.APPLIED
    assert merged.date_applied == date(2026, 5, 1)


def test_pipeline_merge_tags_new_job_as_lead():
    fresh = _job()
    merged = Pipeline._merge_scrape_job(None, fresh, new_status=ApplicationStatus.LEAD)
    assert merged.status == ApplicationStatus.LEAD


def test_approve_and_reject_leads(tmp_path):
    db = Database(tmp_path / "jobs.db")
    lead = _job(status=ApplicationStatus.LEAD, url="https://x.com/lead")
    other = _job(status=ApplicationStatus.LEAD, url="https://x.com/other", title="Staff Security Engineer")
    db.upsert_job(lead)
    db.upsert_job(other)

    assert len(list_pending_leads(db)) == 2
    assert approve_leads(db, [lead.job_id]) == 1
    assert db.get_job(lead.job_id).status == ApplicationStatus.NEW
    assert reject_leads(db, [other.job_id]) == 1
    assert db.get_job(other.job_id).status == ApplicationStatus.REJECTED
    assert len(list_pending_leads(db)) == 0


def test_rejected_lead_excluded_from_export():
    rejected = _job(status=ApplicationStatus.REJECTED, match_score=0.95)
    assert not job_included_in_export(rejected, 0.75)
    assert not job_included_in_export(rejected, None)


def test_search_targets_safe_log_line_omits_pii():
    profile = ResumeSearchProfile(
        search_terms=["Staff Security Engineer"],
        locations=["Remote, USA"],
        remote_preferred=True,
        salary_min=180_000.0,
        source_resume_path=str(Path("resume/test.docx")),
        source_fingerprint="abc123",
        updated_at="2026-01-01T00:00:00Z",
    )
    targets = SearchTargets(
        search_terms=profile.search_terms,
        locations=profile.locations,
        remote_preferred=True,
        salary_min=profile.salary_min,
        candidate_name="Jane Doe",
        profile=profile,
    )
    line = targets.safe_log_line()
    assert "Jane Doe" not in line
    assert "Staff Security Engineer" not in line
    assert "Remote" not in line
    assert "180" not in line
    assert "1 title(s)" in line
    assert "comp floor set" in line


def test_format_lead_preview_escapes_pipe_in_title():
    from agentzero.leads.session import format_lead_preview

    preview = format_lead_preview(
        [_job(title="Staff | Principal Engineer", company="Acme|Corp", match_score=0.9)]
    )
    assert "Staff \\| Principal Engineer" in preview
    assert "Acme\\|Corp" in preview
