"""Tests for sheet → SQLite user-field import."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from agentzero.google.sheet_import import (
    SheetImportResult,
    import_user_fields_to_db,
    merge_user_fields_from_sheet,
    parse_sheet_date,
    parse_sheet_status,
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
    assert parse_sheet_date("2026-05-15T12:00:00Z") == date(2026, 5, 15)
    assert parse_sheet_date("not-a-date") is None


def test_parse_sheet_status():
    assert parse_sheet_status("") is None
    assert parse_sheet_status("applied") == ApplicationStatus.APPLIED
    assert parse_sheet_status("not-a-status") is None


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


def test_merge_no_change_when_empty_row():
    job = _job(notes="keep")
    merged, changed = merge_user_fields_from_sheet(job, {})
    assert not changed
    assert merged.notes == "keep"


def test_sheet_import_result_defaults():
    r = SheetImportResult()
    assert r.updated == 0
    assert r.created == 0


def test_import_user_fields_to_db(tmp_path):
    db = Database(tmp_path / "jobs.db")
    job = _job()
    db.upsert_job(job)

    result = import_user_fields_to_db(
        db,
        {job.job_id: {"date_applied": "2026-04-20", "notes": "referred"}},
    )
    assert result.updated == 1
    assert result.rows_read == 1
    stored = db.get_job(job.job_id)
    assert stored is not None
    assert stored.date_applied == date(2026, 4, 20)
    assert stored.notes == "referred"
    db.close()


def test_import_skips_unknown_job_id(tmp_path):
    db = Database(tmp_path / "jobs.db")
    result = import_user_fields_to_db(db, {"missing-id": {"notes": "x"}})
    assert result.updated == 0
    assert result.skipped_unknown_job_id == 1
    db.close()


def test_import_unchanged_row_not_counted(tmp_path):
    db = Database(tmp_path / "jobs.db")
    job = _job(notes="same")
    db.upsert_job(job)
    result = import_user_fields_to_db(db, {job.job_id: {}})
    assert result.updated == 0
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


def test_sheets_sync_without_import(tmp_path):
    from agentzero.google.sheets import SheetsSync

    db = Database(tmp_path / "jobs.db")
    db.upsert_job(_job())

    class FakeWorksheet:
        def get_all_values(self) -> list:
            return []

        def clear(self) -> None:
            pass

        def update(self, _range: str, values: list) -> None:
            self.last = values

    class FakeSpreadsheet:
        sheet1 = FakeWorksheet()

    sync = SheetsSync(type("C", (), {"open_by_key": lambda s, k: FakeSpreadsheet()})(), "id")
    count, imp = sync.sync(db, import_user_fields=False)
    assert count == 1
    assert imp.updated == 0
    db.close()


def test_sheets_read_job_ids_and_rows(tmp_path):
    from agentzero.google.sheets import SheetsSync

    header = list(SHEET_COLUMNS)
    jid = header.index("job_id")
    row = [""] * len(header)
    row[jid] = "job-1"
    blank = [""] * len(header)
    blank[jid] = "   "

    class Ws:
        def get_all_values(self):
            return [header, row, blank[: jid] + [""]]

    class Sp:
        sheet1 = Ws()

    sync = SheetsSync(type("C", (), {"open_by_key": lambda s, k: Sp()})(), "x")
    assert sync.read_job_ids() == {"job-1"}
    by_id = sync.read_rows_by_job_id()
    assert "job-1" in by_id
    assert sync.read_tracker_rows()[0]["job_id"] == "job-1"
    db.close() if False else None


def test_sheets_read_job_ids_empty_and_missing_column():
    from agentzero.google.sheets import SheetsSync

    class EmptyWs:
        def get_all_values(self):
            return []

    class BadWs:
        def get_all_values(self):
            return [["no_job_id_col"]]

    class Sp:
        def __init__(self, ws):
            self.sheet1 = ws

    sync = SheetsSync(type("C", (), {"open_by_key": lambda s, k: Sp(EmptyWs())})(), "x")
    assert sync.read_job_ids() == set()

    sync2 = SheetsSync(type("C", (), {"open_by_key": lambda s, k: Sp(BadWs())})(), "x")
    with pytest.raises(ValueError, match="job_id"):
        sync2.read_job_ids()


def test_sheets_import_user_fields_delegates(tmp_path, monkeypatch):
    from agentzero.google.sheet_import import SheetImportResult
    from agentzero.google.sheets import SheetsSync

    db = Database(tmp_path / "jobs.db")
    sync = SheetsSync(MagicMock(), "id")
    monkeypatch.setattr(sync, "read_tracker_rows", lambda: [{"job_id": "a"}])
    monkeypatch.setattr(
        "agentzero.google.sheets.import_tracker_rows",
        lambda db, rows, search_terms=None: type(
            "R",
            (),
            {"updated": 2, "created": 1, "skipped": 0, "rows_read": 3},
        )(),
    )
    result = sync.import_user_fields(db, search_terms=["python"])
    assert result.updated == 2
    assert result.created == 1
    assert result.rows_read == 3
    db.close()
