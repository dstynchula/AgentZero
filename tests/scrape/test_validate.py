import pytest

from agentzero.models import JobPosting
from agentzero.scrape.validate import (
    ValidationOutcome,
    apply_aliases,
    assert_source_healthy,
    has_min_role_context,
    parse_comp_from_text,
    reject_incomplete_raw,
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
        "location": "Remote",
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


def test_reject_incomplete_raw_missing_company():
    raw = {"title": "Engineer", "company": "Unknown", "url": "https://x.com/1"}
    assert reject_incomplete_raw(raw) == "missing or placeholder company"


def test_reject_incomplete_raw_missing_location_and_description():
    raw = {
        "title": "Engineer",
        "company": "Acme",
        "url": "https://x.com/1",
    }
    assert reject_incomplete_raw(raw) == (
        "insufficient role context (need location, description, or comp hint)"
    )


def test_validate_raw_accepts_minimal_listing_with_location():
    raw = {
        "title": "Backend Dev",
        "company": "Co",
        "url": "https://jobs.example.com/1",
        "location": "Remote",
    }
    outcome = validate_raw(raw, source="linkedin")
    assert outcome.ok


def test_has_min_role_context_comp_raw():
    assert has_min_role_context({"comp_raw": "$100k - $120k"})


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


def test_parse_comp_rejects_comma_only_junk():
    assert parse_comp_from_text(", - ,") == (None, None, None)
    assert parse_comp_from_text(",000/yr - ") == (None, None, None)


def test_parse_comp_does_not_treat_bare_years_as_salary():
    low, high, _currency = parse_comp_from_text("Senior AI Security Engineer 5-10 years")
    assert low is None and high is None


def test_currency_symbol_mapping():
    from agentzero.scrape.validate import _currency_symbol

    assert _currency_symbol("€") == "EUR"
    assert _currency_symbol(None) is None
    assert _currency_symbol("CHF") == "CHF"


def test_validate_batch_metrics_and_quarantine_list():
    records = [
        {
            "title": "A",
            "company": "C",
            "url": "https://x.com/a",
            "source": "indeed",
            "location": "Remote",
        },
        {
            "job_title": "B",
            "company_name": "C",
            "job_url": "https://x.com/b",
            "salary": "$80,000",
        },
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
    raw = {
        "title": "T",
        "company": "C",
        "url": "https://x.com/1",
        "is_remote": "yes",
        "location": "Remote",
    }
    mapped = apply_aliases(raw, source="indeed")
    outcome = validate_raw(mapped, source="indeed")
    assert outcome.job is not None
    assert outcome.job.remote is True
