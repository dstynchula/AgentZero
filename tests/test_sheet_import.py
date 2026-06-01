"""Tests for sheet → SQLite user-field import."""

from __future__ import annotations

from datetime import date

from agentzero.google.sheet_import import (
    merge_user_fields_from_sheet,
    parse_sheet_date,
)
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.storage.csv_export import SHEET_COLUMNS
from agentzero.storage.db import Database


def _job(**kwargs) -> JobPosting:
    base = dict(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    base.update(kwargs)
    return JobPosting(**base)


def test_parse_sheet_date_formats():
    assert parse_sheet_date("2026-05-15") == date(2026, 5, 15)
    assert parse_sheet_date("5/15/2026") == date(2026, 5, 15)
    assert parse_sheet_date("") is None


def test_merge_date_applied_sets_status_applied():
    job = _job()
    merged, changed = merge_user_fields_from_sheet(job, {"date_applied": "2026-05-01"})
    assert changed
    assert merged.date_applied == date(2026, 5, 1)
    assert merged.status == ApplicationStatus.APPLIED


def test_merge_respects_explicit_status():
    job = _job()
    merged, changed = merge_user_fields_from_sheet(
        job,
        {"date_applied": "2026-05-01", "status": "contacted"},
    )
    assert changed
    assert merged.status == ApplicationStatus.CONTACTED


def test_import_user_fields_to_db(tmp_path):
    from agentzero.google.sheet_import import import_user_fields_to_db

    db = Database(tmp_path / "jobs.db")
    job = _job()
    db.upsert_job(job)

    result = import_user_fields_to_db(
        db,
        {job.job_id: {"date_applied": "2026-04-20", "notes": "referred"}},
    )
    assert result.updated == 1
    stored = db.get_job(job.job_id)
    assert stored is not None
    assert stored.date_applied == date(2026, 4, 20)
    assert stored.notes == "referred"
    db.close()


def test_sheets_sync_imports_before_export(tmp_path):
    from agentzero.google.sheets import SheetsSync

    db = Database(tmp_path / "jobs.db")
    job = _job()
    db.upsert_job(job)

    header = SHEET_COLUMNS
    job_id_col = header.index("job_id")
    applied_col = header.index("date_applied")

    class FakeWorksheet:
        def __init__(self) -> None:
            self.cleared = False
            self.updated: list = []
            row = [""] * len(header)
            row[job_id_col] = job.job_id
            row[applied_col] = "2026-03-10"
            self.values = [header, row]

        def get_all_values(self) -> list:
            return self.values

        def clear(self) -> None:
            self.cleared = True

        def update(self, _range: str, values: list) -> None:
            self.updated = values

    class FakeSpreadsheet:
        def __init__(self) -> None:
            self.sheet1 = FakeWorksheet()

    class FakeClient:
        def open_by_key(self, key: str) -> FakeSpreadsheet:
            return FakeSpreadsheet()

    sync = SheetsSync(FakeClient(), "sheet-id")
    count, import_result = sync.sync(db)
    assert import_result.updated == 1
    assert count == 1
    stored = db.get_job(job.job_id)
    assert stored is not None
    assert stored.date_applied == date(2026, 3, 10)
    assert sync.worksheet.updated[1][applied_col] == "2026-03-10"
    db.close()
