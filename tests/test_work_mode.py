"""Vacuum tests: remote vs in-office work mode → profile → scrape params."""

from __future__ import annotations

import pytest

from agentzero.config import Settings
from agentzero.ingest.search_profile import ResumeSearchProfile, apply_search_profile
from agentzero.ingest.work_mode import (
    REMOTE_USA_CANONICAL,
    apply_work_mode_selection,
    infer_default_work_mode,
    parse_work_mode,
    preview_work_mode_flow,
    selection_from_work_mode,
    trace_scrape_targets,
)


def _profile(**overrides) -> ResumeSearchProfile:
    base = dict(
        search_terms=["Staff Security Engineer"],
        locations=["Remote", "Los Angeles, CA"],
        source_resume_path="resume/test.docx",
        source_fingerprint="abc",
        updated_at="2026-01-01T00:00:00Z",
    )
    base.update(overrides)
    return ResumeSearchProfile(**base)


def test_parse_work_mode_remote_variants():
    assert parse_work_mode("") == "remote"
    assert parse_work_mode("R") == "remote"
    assert parse_work_mode("remote") == "remote"
    assert parse_work_mode("wfh") == "remote"


def test_parse_work_mode_office_variants():
    assert parse_work_mode("I", default="remote") == "in_office"
    assert parse_work_mode("in-office") == "in_office"
    assert parse_work_mode("onsite") == "in_office"


def test_parse_work_mode_invalid():
    with pytest.raises(ValueError, match="Work mode"):
        parse_work_mode("hybrid")


def test_remote_selection_maps_to_usa_remote_filter():
    sel = selection_from_work_mode("remote")
    assert sel.locations == [REMOTE_USA_CANONICAL]
    assert sel.remote_preferred is True
    assert sel.country_indeed == "USA"


def test_office_selection_requires_cities():
    with pytest.raises(ValueError, match="at least one"):
        selection_from_work_mode("in_office", office_locations=[])

    sel = selection_from_work_mode(
        "in_office",
        office_locations=["Los Angeles, CA", "San Francisco, CA"],
    )
    assert sel.locations == ["Los Angeles, CA", "San Francisco, CA"]
    assert sel.remote_preferred is False


def test_remote_trace_uses_united_states_and_omits_hours_old():
    profile = _profile()
    settings = Settings(_env_file=None, search_terms=profile.search_terms, hours_old=168)
    sel = selection_from_work_mode("remote")
    updated = apply_work_mode_selection(profile, sel)
    effective = apply_search_profile(settings, updated)

    rows = trace_scrape_targets(effective)
    assert len(rows) == 1
    assert rows[0]["jobspy_location"] == "United States"
    assert rows[0]["is_remote"] is True
    assert rows[0]["hours_old"] is None


def test_office_trace_keeps_city_and_hours_old():
    profile = _profile()
    settings = Settings(_env_file=None, search_terms=profile.search_terms, hours_old=168)
    sel = selection_from_work_mode(
        "in_office",
        office_locations=["Los Angeles, CA"],
    )
    updated = apply_work_mode_selection(profile, sel)
    effective = apply_search_profile(settings, updated)

    rows = trace_scrape_targets(effective)
    assert len(rows) == 1
    assert rows[0]["jobspy_location"] == "Los Angeles, CA"
    assert rows[0]["is_remote"] is False
    assert rows[0]["hours_old"] == 168


def test_infer_default_remote_from_profile():
    assert infer_default_work_mode(_profile(locations=["remote - usa"])) == "remote"
    assert infer_default_work_mode(_profile(remote_preferred=True)) == "remote"


def test_infer_default_office_when_cities_present():
    assert infer_default_work_mode(_profile(locations=["Los Angeles, CA"])) == "in_office"


def test_preview_work_mode_flow_end_to_end():
    profile = _profile()
    settings = Settings(_env_file=None, search_terms=profile.search_terms, hours_old=168)
    sel = selection_from_work_mode("remote")
    trace = preview_work_mode_flow(profile, sel, settings)

    assert trace["work_mode"] == "remote"
    assert trace["profile_locations"] == [REMOTE_USA_CANONICAL]
    assert trace["profile_remote_preferred"] is True
    assert trace["scrape_targets"][0]["is_remote"] is True
