from datetime import date

import pytest
from pydantic import ValidationError

from agentzero.models import ApplicationStatus, JobPosting, stable_job_id


def test_stable_job_id_is_deterministic():
    kwargs = dict(
        source="indeed",
        company="Acme Corp",
        title="Software Engineer",
        url="https://example.com/jobs/1",
    )
    assert stable_job_id(**kwargs) == stable_job_id(**kwargs)


def test_stable_job_id_normalizes_whitespace_and_case():
    a = stable_job_id(
        source="Indeed",
        company="  Acme   Corp ",
        title="Software Engineer",
        url="https://example.com/jobs/1",
    )
    b = stable_job_id(
        source="indeed",
        company="acme corp",
        title="software engineer",
        url="https://example.com/jobs/1",
    )
    assert a == b


def test_job_posting_required_fields():
    job = JobPosting(
        title="Backend Engineer",
        company="Example Inc",
        url="https://jobs.example.com/1",
        source="linkedin",
    )
    assert job.title == "Backend Engineer"
    assert job.status == ApplicationStatus.NEW
    assert len(job.job_id) == 16


def test_job_posting_accepts_company_website():
    job = JobPosting(
        title="Role",
        company="Co",
        url="https://x.com/1",
        source="indeed",
        company_website="https://www.co.com/",
    )
    assert job.company_website == "https://www.co.com/"


def test_job_posting_public_company_fields():
    job = JobPosting(
        title="Role",
        company="Co",
        url="https://x.com/1",
        source="indeed",
        is_public_company=True,
        stock_ticker="ACME",
    )
    assert job.is_public_company is True
    assert job.stock_ticker == "ACME"


def test_linkedin_connections_field_optional_null():
    job = JobPosting(
        title="Role",
        company="Co",
        url="https://x.com/1",
        source="linkedin",
        linkedin_connections_note=None,
    )
    assert job.linkedin_connections_note is None


def test_job_posting_apply_url_fields():
    job = JobPosting(
        title="Role",
        company="Co",
        url="https://x.com/1",
        source="indeed",
        apply_url="https://apply.example.com/1",
        easy_apply_url="https://easy.example.com/1",
        easy_apply=True,
    )
    assert job.apply_url == "https://apply.example.com/1"
    assert job.easy_apply is True


def test_job_posting_optional_fields_nullable():
    job = JobPosting(
        title="Role",
        company="Co",
        url="https://x.com/1",
        source="glassdoor",
        comp_min=None,
        comp_max=None,
        glassdoor_rating=None,
        company_size=None,
    )
    assert job.comp_min is None
    assert job.glassdoor_rating is None


def test_stable_job_id_linkedin_uses_numeric_posting_id_only():
    slug_url = "https://www.linkedin.com/jobs/view/staff-security-engineer-4328174567"
    numeric_url = "https://www.linkedin.com/jobs/view/4328174567"
    a = stable_job_id(
        source="linkedin",
        company="Garner Health",
        title="Staff Security Engineer",
        url=slug_url,
    )
    b = stable_job_id(
        source="linkedin",
        company="Garner",
        title="Different Title Text",
        url=numeric_url,
    )
    assert a == b


def test_job_posting_job_id_matches_stable_job_id():
    job = JobPosting(
        title="Data Engineer",
        company="DataCo",
        url="https://example.com/2",
        source="zip_recruiter",
    )
    assert job.job_id == stable_job_id(
        source=job.source,
        company=job.company,
        title=job.title,
        url=job.url,
    )


def test_job_posting_rejects_missing_required():
    with pytest.raises(ValidationError):
        JobPosting(title="Only Title", company="Co", url="https://x.com", source="")


def test_job_posting_rejects_blank_url_after_strip():
    with pytest.raises(ValidationError):
        JobPosting(title="T", company="C", url="   ", source="indeed")


def test_job_posting_rejects_invalid_glassdoor_rating():
    with pytest.raises(ValidationError, match="glassdoor_rating"):
        JobPosting(
            title="T",
            company="C",
            url="https://x.com/1",
            source="indeed",
            glassdoor_rating=6.0,
        )


def test_job_posting_accepts_glassdoor_rating_boundaries():
    for rating in (0.0, 5.0, 3.5):
        job = JobPosting(
            title="T",
            company="C",
            url="https://x.com/1",
            source="indeed",
            glassdoor_rating=rating,
        )
        assert job.glassdoor_rating == rating


def test_job_posting_accepts_optional_enrichment():
    job = JobPosting(
        title="Staff Engineer",
        company="BigCo",
        url="https://jobs.bigco.com/99",
        source="google",
        comp_min=150_000,
        comp_max=200_000,
        currency="USD",
        company_size="1001-5000",
        glassdoor_rating=4.2,
        glassdoor_reviews=1200,
        date_posted=date(2026, 5, 1),
        location="Remote",
        remote=True,
        match_score=0.87,
        status=ApplicationStatus.QUEUED,
        date_first_contacted=date(2026, 5, 10),
    )
    assert job.comp_min == 150_000
    assert job.remote is True
    assert job.status == ApplicationStatus.QUEUED
