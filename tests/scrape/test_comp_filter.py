"""Tests for salary-floor comp filtering."""

from agentzero.models import JobPosting
from agentzero.scrape.comp_filter import (
    filter_by_salary_floor,
    meets_salary_floor,
    posted_comp_ceiling,
)


def _job(**kwargs) -> JobPosting:
    base = dict(
        title="Engineer",
        company="Acme",
        url="https://example.com/j/1",
        source="test",
    )
    base.update(kwargs)
    return JobPosting.model_validate(base)


def test_posted_comp_ceiling_prefers_max():
    assert posted_comp_ceiling(_job(comp_min=100_000, comp_max=150_000)) == 150_000


def test_posted_comp_ceiling_falls_back_to_min():
    assert posted_comp_ceiling(_job(comp_min=200_000)) == 200_000


def test_meets_salary_floor_when_ceiling_at_or_above():
    job = _job(comp_min=180_000, comp_max=240_000)
    assert meets_salary_floor(job, 230_000) is True


def test_meets_salary_floor_rejects_below():
    job = _job(comp_min=150_000, comp_max=210_000)
    assert meets_salary_floor(job, 230_000) is False


def test_meets_salary_floor_keeps_unknown_comp():
    assert meets_salary_floor(_job(), 230_000) is True


def test_filter_by_salary_floor_splits():
    jobs = [
        _job(comp_max=250_000, url="https://example.com/a"),
        _job(comp_max=200_000, url="https://example.com/b"),
    ]
    kept, rejected = filter_by_salary_floor(jobs, 230_000)
    assert len(kept) == 1
    assert len(rejected) == 1
    assert kept[0].url.endswith("/a")
