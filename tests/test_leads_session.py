"""Tests for lead-gathering session and LEAD status lifecycle."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from agentzero.apply.sheet_fields import merge_user_fields_from_sheet
from agentzero.config import Settings
from agentzero.google.sync import SheetSyncResult
from agentzero.ingest.resume import ResumeProfile
from agentzero.ingest.search_profile import ResumeSearchProfile
from agentzero.leads.session import (
    LeadRunResult,
    SearchTargets,
    approve_leads,
    build_run_settings,
    check_board_sessions,
    commit_leads,
    format_lead_preview,
    job_to_preview_dict,
    list_pending_leads,
    reject_leads,
    run_lead_scrape,
    suggest_targets,
)
from agentzero.loops.pipeline import Pipeline, PipelineResult
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.rank.export_filter import job_included_in_export
from agentzero.scrape.browser_session import SessionState
from agentzero.scrape.session_probe import SessionProbeResult
from agentzero.storage.db import Database


def _sample_profile(resume_path: Path = Path("resume/test.docx")) -> ResumeSearchProfile:
    return ResumeSearchProfile(
        search_terms=["Staff Security Engineer"],
        locations=["Remote, USA"],
        remote_preferred=True,
        salary_min=180_000.0,
        source_resume_path=str(resume_path),
        source_fingerprint="abc123",
        updated_at="2026-01-01T00:00:00Z",
    )


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
    profile = _sample_profile()
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
    preview = format_lead_preview(
        [_job(title="Staff | Principal Engineer", company="Acme|Corp", match_score=0.9)]
    )
    assert "Staff \\| Principal Engineer" in preview
    assert "Acme\\|Corp" in preview


def test_search_targets_summary():
    profile = _sample_profile()
    targets = SearchTargets(
        search_terms=profile.search_terms,
        locations=profile.locations,
        remote_preferred=True,
        salary_min=profile.salary_min,
        candidate_name="Jane Doe",
        profile=profile,
    )
    assert "Staff Security Engineer" in targets.summary()


def test_lead_run_result_lead_count():
    result = LeadRunResult(
        pipeline=PipelineResult(scraped=2),
        leads=[_job(url="https://x.com/a"), _job(url="https://x.com/b")],
    )
    assert result.lead_count == 2


def test_suggest_targets(monkeypatch):
    profile = _sample_profile()
    resume = ResumeProfile(raw_text="text", source_path="resume/r.docx", name="Jane Doe")
    monkeypatch.setattr(
        "agentzero.leads.session.resolve_search_from_resume",
        lambda **kwargs: profile,
    )
    monkeypatch.setattr(
        "agentzero.ingest.resume.ingest_resume",
        lambda **kwargs: resume,
    )
    targets = suggest_targets(MagicMock())
    assert targets.candidate_name == "Jane Doe"
    assert targets.remote_preferred is True
    assert targets.search_terms == profile.search_terms


def test_suggest_targets_infers_remote_from_locations(monkeypatch):
    profile = _sample_profile().model_copy(
        update={"remote_preferred": False, "locations": ["remote - usa"]}
    )
    resume = ResumeProfile(raw_text="text", source_path="resume/r.docx")
    monkeypatch.setattr(
        "agentzero.leads.session.resolve_search_from_resume",
        lambda **kwargs: profile,
    )
    monkeypatch.setattr(
        "agentzero.ingest.resume.ingest_resume",
        lambda **kwargs: resume,
    )
    targets = suggest_targets(MagicMock())
    assert targets.remote_preferred is True


def test_build_run_settings_remote_overrides(tmp_path, monkeypatch):
    saved: list[ResumeSearchProfile] = []

    def capture_save(profile: ResumeSearchProfile, resume_dir: Path = Path("resume")) -> Path:
        saved.append(profile)
        return tmp_path / "search_profile.json"

    monkeypatch.setattr("agentzero.leads.session.save_search_profile", capture_save)
    profile = _sample_profile()
    base = Settings(_env_file=None, remote_only=False, results_wanted=50)

    merged = build_run_settings(
        base,
        profile,
        search_terms=["Staff Engineer"],
        remote_only=True,
        salary_min=200_000.0,
        results_wanted=30,
        primary_query_only=True,
    )

    assert merged.search_terms == ["Staff Engineer"]
    assert merged.salary_min == 200_000.0
    assert merged.results_wanted == 30
    assert merged.scrape_primary_query_only is True
    assert merged.remote_only is True
    assert saved[-1].search_terms == ["Staff Engineer"]
    assert saved[-1].salary_min == 200_000.0


def test_build_run_settings_in_office_locations(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentzero.leads.session.save_search_profile",
        lambda profile, resume_dir=Path("resume"): tmp_path / "search_profile.json",
    )
    profile = _sample_profile().model_copy(update={"remote_preferred": False})
    base = Settings(_env_file=None, remote_only=False)

    merged = build_run_settings(
        base,
        profile,
        locations=["Los Angeles, CA"],
        remote_only=False,
    )

    assert merged.remote_only is False
    assert "Los Angeles, CA" in merged.locations


def test_check_board_sessions_parses_csv_sites(monkeypatch):
    settings = Settings(_env_file=None, scrape_browser_sites="indeed, glassdoor")
    seen: list[str] = []

    def fake_probe(_settings: Settings, site: str) -> SessionProbeResult:
        seen.append(site)
        return SessionProbeResult(
            site=site,
            state=SessionState.READY,
            url=f"https://{site}.example/jobs",
            listing_count=3,
        )

    monkeypatch.setattr("agentzero.scrape.session_probe.probe_browser_session", fake_probe)
    results = check_board_sessions(settings)
    assert seen == ["indeed", "glassdoor"]
    assert len(results) == 2
    assert results[0].listing_count == 3


def test_check_board_sessions_accepts_list_sites(monkeypatch):
    settings = Settings(_env_file=None, scrape_browser_sites=["linkedin"])
    monkeypatch.setattr(
        "agentzero.scrape.session_probe.probe_browser_session",
        lambda _settings, site: SessionProbeResult(
            site=site,
            state=SessionState.READY,
            url="https://linkedin.example/jobs",
        ),
    )
    results = check_board_sessions(settings)
    assert len(results) == 1
    assert results[0].site == "linkedin"


def test_run_lead_scrape_collects_new_leads(tmp_path, monkeypatch):
    db = Database(tmp_path / "jobs.db")
    existing = _job(status=ApplicationStatus.NEW, url="https://x.com/existing")
    db.upsert_job(existing)
    new_lead = _job(
        status=ApplicationStatus.LEAD,
        url="https://x.com/new",
        match_score=0.91,
    )
    pipeline_result = PipelineResult(scraped=1, ranked=1)

    class FakePipeline:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run(self, **kwargs):
            db.upsert_job(new_lead)
            return pipeline_result

    monkeypatch.setattr("agentzero.scrape.factory.build_scrape_source", lambda *args, **kwargs: object())
    monkeypatch.setattr("agentzero.leads.session.Pipeline", FakePipeline)

    settings = Settings(_env_file=None, max_concurrency=2)
    result = run_lead_scrape(db, settings, llm=None, profile=None)

    assert result.lead_count == 1
    assert result.leads[0].job_id == new_lead.job_id
    assert result.pipeline.scraped == 1


def test_approve_leads_skips_non_lead_and_missing(tmp_path):
    db = Database(tmp_path / "jobs.db")
    active = _job(status=ApplicationStatus.NEW, url="https://x.com/active")
    db.upsert_job(active)
    assert approve_leads(db, [active.job_id, "missing-id"]) == 0


def test_reject_leads_skips_non_lead_and_missing(tmp_path):
    db = Database(tmp_path / "jobs.db")
    active = _job(status=ApplicationStatus.NEW, url="https://x.com/active")
    db.upsert_job(active)
    assert reject_leads(db, [active.job_id, "missing-id"]) == 0


def test_commit_leads_approves_and_syncs(tmp_path, monkeypatch):
    db = Database(tmp_path / "jobs.db")
    lead = _job(status=ApplicationStatus.LEAD, url="https://x.com/lead")
    db.upsert_job(lead)
    settings = Settings(_env_file=None, sheet_id="abc123")
    sync_result = SheetSyncResult(
        row_count=1,
        spreadsheet_title="AgentZero Sheet",
        imported=0,
        created=0,
        skipped_unknown_job_id=0,
    )
    monkeypatch.setattr(
        "agentzero.google.sync.sync_jobs_to_sheet",
        lambda **kwargs: sync_result,
    )

    result = commit_leads(db, settings, [lead.job_id])

    assert result.approved == 1
    assert result.sync.row_count == 1
    assert db.get_job(lead.job_id).status == ApplicationStatus.NEW


def test_job_to_preview_dict_truncates_rationale():
    job = _job(match_score=0.82, match_rationale="x" * 250)
    preview = job_to_preview_dict(job)
    assert preview["job_id"] == job.job_id
    assert len(str(preview["match_rationale"])) == 200


def test_format_lead_preview_empty():
    assert format_lead_preview([]) == "No new leads from this run."
