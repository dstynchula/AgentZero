"""Tests for sheet field parsing and merge from tracker rows."""

from __future__ import annotations

from datetime import date

from agentzero.apply.sheet_fields import (
    merge_user_fields_from_sheet,
    parse_sheet_date,
    parse_sheet_status,
)
from agentzero.models import ApplicationStatus, JobPosting


def _job(**kwargs) -> JobPosting:
    base = dict(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    base.update(kwargs)
    return JobPosting(**base)


def test_parse_sheet_date_iso():
    assert parse_sheet_date("2026-05-01") == date(2026, 5, 1)


def test_parse_sheet_date_iso_datetime_prefix():
    assert parse_sheet_date("2026-05-01T12:30:00Z") == date(2026, 5, 1)


def test_parse_sheet_date_us_slash():
    assert parse_sheet_date("5/1/2026") == date(2026, 5, 1)


def test_parse_sheet_date_two_digit_year():
    assert parse_sheet_date("5/1/26") == date(2026, 5, 1)


def test_parse_sheet_date_invalid_returns_none():
    assert parse_sheet_date("not-a-date") is None
    assert parse_sheet_date("13/40/2026") is None
    assert parse_sheet_date(None) is None
    assert parse_sheet_date("") is None


def test_parse_sheet_status_valid_and_invalid():
    assert parse_sheet_status("applied") == ApplicationStatus.APPLIED
    assert parse_sheet_status("interviewing") == ApplicationStatus.INTERVIEWING
    assert parse_sheet_status("  OFFER  ") == ApplicationStatus.OFFER
    assert parse_sheet_status("") is None
    assert parse_sheet_status("not-a-status") is None


def test_merge_user_fields_no_changes():
    job = _job(status=ApplicationStatus.NEW)
    merged, changed = merge_user_fields_from_sheet(job, {})
    assert merged is job
    assert changed is False


def test_merge_user_fields_date_first_contacted_and_notes():
    job = _job(status=ApplicationStatus.NEW)
    merged, changed = merge_user_fields_from_sheet(
        job,
        {
            "date_first_contacted": "2026-04-01",
            "notes": "  follow up  ",
        },
    )
    assert changed
    assert merged.date_first_contacted == date(2026, 4, 1)
    assert merged.notes == "follow up"


def test_merge_user_fields_explicit_status():
    job = _job(status=ApplicationStatus.NEW)
    merged, changed = merge_user_fields_from_sheet(job, {"status": "reviewed"})
    assert changed
    assert merged.status == ApplicationStatus.REVIEWED


def test_merge_user_fields_date_applied_does_not_promote_applied_status():
    job = _job(status=ApplicationStatus.APPLIED, date_applied=date(2026, 5, 1))
    merged, changed = merge_user_fields_from_sheet(job, {"date_applied": "2026-05-02"})
    assert changed
    assert merged.date_applied == date(2026, 5, 2)
    assert merged.status == ApplicationStatus.APPLIED
