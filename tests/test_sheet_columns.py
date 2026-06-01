"""Tests for slim Google Sheet export columns."""

from __future__ import annotations

from agentzero.models import JobPosting
from agentzero.storage.csv_export import (
    EXPORT_COLUMNS,
    SHEET_COLUMNS,
    job_to_row,
    job_to_sheet_row,
)


def test_sheet_columns_are_subset_of_export():
    assert set(SHEET_COLUMNS) <= set(EXPORT_COLUMNS)
    assert len(SHEET_COLUMNS) == 13
    assert len(EXPORT_COLUMNS) == 24


def test_job_to_sheet_row_omits_internal_fields():
    job = JobPosting(
        title="Security Engineer",
        company="Acme",
        url="https://example.com/j",
        source="linkedin",
        match_score=0.9,
        remote=True,
        careers_url="https://example.com/careers",
    )
    sheet = job_to_sheet_row(job)
    full = job_to_row(job)
    assert set(sheet.keys()) == set(SHEET_COLUMNS)
    assert "remote" not in sheet
    assert "match_tier" not in sheet
    assert "careers_url" not in sheet
    assert sheet["match_score"] == full["match_score"]
