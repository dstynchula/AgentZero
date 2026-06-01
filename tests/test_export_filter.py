"""Tests for match-score export filtering."""

from __future__ import annotations

from datetime import date

from agentzero.models import JobPosting
from agentzero.rank.export_filter import filter_jobs_for_export, job_included_in_export


def _job(**kwargs) -> JobPosting:
    base = dict(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    base.update(kwargs)
    return JobPosting(**base)


def test_below_floor_excluded():
    job = _job(match_score=0.25)
    assert not job_included_in_export(job, 0.75)


def test_at_floor_included():
    job = _job(match_score=0.75)
    assert job_included_in_export(job, 0.75)


def test_unranked_included_until_scored():
    job = _job(match_score=None)
    assert job_included_in_export(job, 0.75)


def test_applied_job_always_exports():
    job = _job(match_score=0.15, date_applied=date(2026, 5, 1))
    assert job_included_in_export(job, 0.75)


def test_filter_jobs_for_export():
    jobs = [_job(match_score=0.9), _job(match_score=0.4), _job(match_score=None)]
    kept, rejected = filter_jobs_for_export(jobs, 0.75)
    assert len(kept) == 2
    assert len(rejected) == 1
    assert rejected[0].match_score == 0.4


def test_filter_disabled_when_min_score_zero():
    jobs = [_job(match_score=0.1)]
    kept, rejected = filter_jobs_for_export(jobs, 0)
    assert kept == jobs
    assert rejected == []


def test_lead_always_excluded():
    from agentzero.models import ApplicationStatus

    job = _job(match_score=0.99, status=ApplicationStatus.LEAD)
    assert not job_included_in_export(job, None)
    assert not job_included_in_export(job, 0)


def test_rejected_lead_always_excluded():
    from agentzero.models import ApplicationStatus

    job = _job(match_score=0.99, status=ApplicationStatus.REJECTED)
    assert not job_included_in_export(job, None)
    assert not job_included_in_export(job, 0.75)


def test_filter_excludes_lead_when_min_score_disabled():
    from agentzero.models import ApplicationStatus

    lead = _job(match_score=0.99, status=ApplicationStatus.LEAD)
    kept, rejected = filter_jobs_for_export([lead], 0)
    assert kept == []
    assert rejected == [lead]

def test_applied_status_always_exports():
    from agentzero.models import ApplicationStatus

    job = _job(match_score=0.1, status=ApplicationStatus.APPLIED)
    assert job_included_in_export(job, 0.75)


def test_offer_status_always_exports():
    from agentzero.models import ApplicationStatus

    job = _job(match_score=0.1, status=ApplicationStatus.OFFER)
    assert job_included_in_export(job, 0.75)
