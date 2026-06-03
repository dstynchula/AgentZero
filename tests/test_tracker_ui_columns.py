"""Tests for web tracker table columns."""

from __future__ import annotations

from agentzero.models import JobPosting
from agentzero.storage.csv_export import (
    EXPORT_COLUMNS,
    TRACKER_UI_COLUMNS,
    job_to_row,
    job_to_tracker_ui_row,
)


def test_tracker_ui_columns_are_subset_of_export():
    assert set(TRACKER_UI_COLUMNS) <= set(EXPORT_COLUMNS)
    assert len(TRACKER_UI_COLUMNS) == 13
    assert len(EXPORT_COLUMNS) == 27


def test_job_to_tracker_ui_row_omits_internal_fields():
    job = JobPosting(
        title="Security Engineer",
        company="Acme",
        url="https://example.com/j",
        source="linkedin",
        match_score=0.9,
        remote=True,
        careers_url="https://example.com/careers",
    )
    ui = job_to_tracker_ui_row(job)
    full = job_to_row(job)
    assert set(ui.keys()) == set(TRACKER_UI_COLUMNS)
    assert "remote" not in ui
    assert "match_tier" not in ui
    assert "careers_url" not in ui
    assert ui["match_score"] == full["match_score"]
