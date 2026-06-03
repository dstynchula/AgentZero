"""Tests for Scraper search-targets validation and apply layer."""

from __future__ import annotations

import pytest

from agentzero.config import Settings
from agentzero.ingest.search_profile import ResumeSearchProfile
from agentzero.web.operator_config import OperatorScrapeConfig
from agentzero.web.search_targets import (
    MAX_LOCATIONS,
    apply_operator_search_targets,
    effective_search_targets_form,
    operator_search_targets_patch,
    parse_salary_min_field,
    parse_search_targets_form,
    sanitize_free_text,
    search_targets_configured,
)


def test_parse_search_targets_remote_usa():
    parsed = parse_search_targets_form(
        work_mode="remote",
        locations_text="ignored",
        salary_min_text="180000",
        scrape_remote_only=True,
    )
    assert parsed.work_mode == "remote"
    assert parsed.locations == ["remote - usa"]
    assert parsed.salary_min == 180000.0
    assert parsed.scrape_remote_only is True


def test_parse_search_targets_in_office_requires_location():
    with pytest.raises(ValueError, match="at least one location"):
        parse_search_targets_form(
            work_mode="in_office",
            locations_text="",
            salary_min_text="",
            scrape_remote_only=False,
        )


def test_parse_search_targets_in_office_valid():
    parsed = parse_search_targets_form(
        work_mode="in_office",
        locations_text="Los Angeles, CA; San Francisco, CA",
        salary_min_text="",
        scrape_remote_only=False,
    )
    assert parsed.work_mode == "in_office"
    assert "Los Angeles, CA" in parsed.locations


def test_parse_search_targets_rejects_hostile_location():
    with pytest.raises(ValueError, match="invalid characters"):
        parse_search_targets_form(
            work_mode="in_office",
            locations_text="<script>alert(1)</script>",
            salary_min_text="",
            scrape_remote_only=False,
        )


def test_parse_search_targets_rejects_too_many_locations():
    locs = ", ".join(f"City{i}, ST" for i in range(MAX_LOCATIONS + 1))
    with pytest.raises(ValueError, match="At most"):
        parse_search_targets_form(
            work_mode="in_office",
            locations_text=locs,
            salary_min_text="",
            scrape_remote_only=False,
        )


def test_parse_salary_min_rejects_nan():
    with pytest.raises(ValueError, match="number"):
        parse_salary_min_field("nan")


def test_parse_salary_min_rejects_negative():
    with pytest.raises(ValueError, match="non-negative"):
        parse_salary_min_field("-1")


def test_parse_salary_min_rejects_huge():
    with pytest.raises(ValueError, match="at most"):
        parse_salary_min_field("99999999999")


def test_sanitize_free_text_rejects_control_chars():
    with pytest.raises(ValueError, match="invalid characters"):
        sanitize_free_text("a\x00b", max_len=10, field_name="X")


def test_apply_operator_search_targets_noop_when_not_configured():
    settings = Settings(_env_file=None, locations=["Remote"], remote_only=False)
    assert apply_operator_search_targets(settings, None) is settings
    op = OperatorScrapeConfig()
    assert apply_operator_search_targets(settings, op) is settings


def test_apply_operator_search_targets_remote():
    settings = Settings(_env_file=None, locations=["NYC"], remote_only=False, salary_min=None)
    op = OperatorScrapeConfig(
        work_mode="remote",
        locations=["remote - usa"],
        salary_min=200_000.0,
        scrape_remote_only=True,
        search_targets_configured=True,
    )
    out = apply_operator_search_targets(settings, op)
    assert out.locations == ["remote - usa"]
    assert out.remote_only is True
    assert out.salary_min == 200_000.0


def test_effective_search_targets_form_uses_profile_when_not_configured():
    profile = ResumeSearchProfile(
        search_terms=["Engineer"],
        locations=["remote - usa"],
        remote_preferred=True,
        salary_min=150_000.0,
        country_indeed="USA",
        source_resume_path="resume/test.pdf",
        source_fingerprint="abc",
        updated_at="2026-01-01T00:00:00Z",
    )
    form = effective_search_targets_form(
        profile,
        None,
        settings=Settings(_env_file=None, remote_only=True),
    )
    assert form["work_mode"] == "remote"
    assert form["salary_min"] == "150000"
    assert form["scrape_remote_only"] is True
    assert form["configured"] is False


def test_search_targets_configured_flag():
    assert search_targets_configured(OperatorScrapeConfig(search_targets_configured=True))
    assert not search_targets_configured(OperatorScrapeConfig())


def test_operator_search_targets_patch():
    parsed = parse_search_targets_form(
        work_mode="remote",
        locations_text="",
        salary_min_text="",
        scrape_remote_only=False,
    )
    patch = operator_search_targets_patch(parsed)
    assert patch["search_targets_configured"] is True
    assert patch["work_mode"] == "remote"
