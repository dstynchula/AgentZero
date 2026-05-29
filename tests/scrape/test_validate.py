import pytest

from agentzero.models import JobPosting
from agentzero.scrape.validate import (
    ValidationOutcome,
    apply_aliases,
    assert_source_healthy,
    parse_comp_from_text,
    validate_batch,
    validate_raw,
)


def test_apply_aliases_keeps_first_non_empty_value_on_collision():
    raw = {"title": "First", "job_title": "Second", "company": "Co", "url": "https://x.com/1"}
    mapped = apply_aliases(raw, source="indeed")
    assert mapped["title"] == "First"


def test_apply_aliases_maps_job_title_and_company():
    raw = {"job_title": "Engineer", "company_name": "Acme", "job_url": "https://x.com/1"}
    mapped = apply_aliases(raw, source="indeed")
    assert mapped["title"] == "Engineer"
    assert mapped["company"] == "Acme"
    assert mapped["url"] == "https://x.com/1"
    assert mapped["source"] == "indeed"


def test_validate_raw_accepts_valid_record():
    raw = {
        "title": "Backend Dev",
        "company": "Co",
        "url": "https://jobs.example.com/1",
        "source": "linkedin",
    }
    outcome = validate_raw(raw, source="linkedin")
    assert outcome.ok
    assert isinstance(outcome.job, JobPosting)


def test_validate_raw_repairs_via_aliases():
    raw = {
        "job_title": "Data Engineer",
        "company_name": "DataCo",
        "job_url": "https://jobs.example.com/2",
        "salary": "$120,000 - $150,000",
    }
    outcome = validate_raw(raw, source="indeed")
    assert outcome.ok
    assert outcome.repaired
    assert outcome.job is not None
    assert outcome.job.comp_min == 120_000
    assert outcome.job.comp_max == 150_000
    assert outcome.job.currency == "USD"
    assert outcome.job.comp_is_estimate is True


def test_validate_raw_quarantines_unfixable():
    raw = {"job_title": "No URL role", "company_name": "Co"}
    outcome = validate_raw(raw, source="glassdoor")
    assert not outcome.ok
    assert outcome.quarantined
    assert outcome.error


def test_parse_comp_range_with_commas_and_dual_currency_symbols():
    low, high, currency = parse_comp_from_text("$120,000 - $150,000")
    assert low == 120_000
    assert high == 150_000
    assert currency == "USD"


def test_parse_comp_single_and_k_suffix():
    low, high, currency = parse_comp_from_text("$90k")
    assert low == 90_000
    assert high == 90_000
    assert currency == "USD"


def test_parse_comp_empty_returns_none():
    assert parse_comp_from_text("") == (None, None, None)
    assert parse_comp_from_text("not a salary") == (None, None, None)


def test_currency_symbol_mapping():
    from agentzero.scrape.validate import _currency_symbol

    assert _currency_symbol("€") == "EUR"
    assert _currency_symbol(None) is None
    assert _currency_symbol("CHF") == "CHF"


def test_validate_batch_metrics_and_quarantine_list():
    records = [
        {"title": "A", "company": "C", "url": "https://x.com/a", "source": "indeed"},
        {"job_title": "B", "company_name": "C", "job_url": "https://x.com/b"},
        {"title": "broken"},
    ]
    jobs, quarantined, metrics = validate_batch(records, source="indeed")
    assert len(jobs) == 2
    assert len(quarantined) == 1
    assert metrics["valid_pct"] == pytest.approx(66.666, rel=0.01)
    assert metrics["quarantined_pct"] == pytest.approx(33.333, rel=0.01)


def test_validate_batch_empty_metrics():
    jobs, quarantined, metrics = validate_batch([], source="indeed")
    assert jobs == []
    assert quarantined == []
    assert metrics["valid_pct"] == 100.0


def test_assert_source_healthy_raises_below_threshold():
    with pytest.raises(RuntimeError, match="health check failed"):
        assert_source_healthy({"total": 10, "valid_pct": 50.0}, min_valid_pct=80.0)


def test_assert_source_healthy_passes():
    assert_source_healthy({"total": 10, "valid_pct": 90.0})


def test_validation_outcome_ok_property():
    job = JobPosting(title="T", company="C", url="https://x.com/1", source="indeed")
    assert ValidationOutcome(job=job).ok
    assert not ValidationOutcome(job=None, error="x").ok


def test_apply_aliases_coerces_remote_string():
    raw = {"title": "T", "company": "C", "url": "https://x.com/1", "is_remote": "yes"}
    mapped = apply_aliases(raw, source="zip_recruiter")
    outcome = validate_raw(mapped, source="zip_recruiter")
    assert outcome.job is not None
    assert outcome.job.remote is True
