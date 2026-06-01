"""Tests for Google sync prune planning and execution."""

from __future__ import annotations

import pytest

from agentzero.config import Settings
from agentzero.google.sync import PrunePlan, plan_prune_db_to_sheet, prune_db_to_sheet
from agentzero.models import JobPosting
from agentzero.storage.db import Database
from tests.test_sync_scripts import FakeSpreadsheet


def test_prune_plan_dataclass():
    plan = PrunePlan(
        spreadsheet_title="Jobs",
        sheet_job_count=2,
        db_job_count=5,
        to_delete=["a", "b", "c"],
        missing_in_db=["x"],
    )
    assert len(plan.to_delete) == 3
    assert plan.missing_in_db == ["x"]


def _settings(tmp_path) -> Settings:
    settings = Settings(
        _env_file=None,
        sheet_id="abc123",
        google_client_secret=tmp_path / "secret.json",
        google_token_path=tmp_path / "token.json",
    )
    settings.google_client_secret.write_text("{}", encoding="utf-8")
    settings.google_token_path.write_text("{}", encoding="utf-8")
    return settings


def test_plan_prune_db_to_sheet(tmp_path, monkeypatch):
    db = Database(tmp_path / "jobs.db")
    on_sheet = JobPosting(title="A", company="Co", url="https://a.com/1", source="indeed")
    only_db = JobPosting(title="B", company="Co", url="https://a.com/2", source="indeed")
    db.upsert_job(on_sheet)
    db.upsert_job(only_db)

    class Ws:
        def get_all_values(self):
            from agentzero.storage.csv_export import SHEET_COLUMNS

            header = list(SHEET_COLUMNS)
            col = header.index("job_id")
            row = [""] * len(header)
            row[col] = on_sheet.job_id
            return [header, row]

    class Sp(FakeSpreadsheet):
        def __init__(self):
            super().__init__()
            self.sheet1 = Ws()

    monkeypatch.setattr(
        "agentzero.google.sync.load_credentials",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "agentzero.google.sync.authorize_gspread",
        lambda creds: type("Client", (), {"open_by_key": lambda self, k: Sp()})(),
    )
    monkeypatch.setattr(
        "agentzero.google.client.open_spreadsheet",
        lambda creds, sheet_id: Sp(),
    )

    plan = plan_prune_db_to_sheet(db=db, settings=_settings(tmp_path))
    assert plan.sheet_job_count == 1
    assert plan.db_job_count == 2
    assert only_db.job_id in plan.to_delete
    assert on_sheet.job_id not in plan.to_delete
    db.close()


def test_prune_db_to_sheet_deletes_extras(tmp_path, monkeypatch):
    db = Database(tmp_path / "jobs.db")
    on_sheet = JobPosting(title="A", company="Co", url="https://a.com/1", source="indeed")
    extra = JobPosting(title="B", company="Co", url="https://a.com/2", source="indeed")
    db.upsert_job(on_sheet)
    db.upsert_job(extra)

    class Ws:
        def get_all_values(self):
            from agentzero.storage.csv_export import SHEET_COLUMNS

            header = list(SHEET_COLUMNS)
            col = header.index("job_id")
            row = [""] * len(header)
            row[col] = on_sheet.job_id
            return [header, row]

    class Sp(FakeSpreadsheet):
        def __init__(self):
            super().__init__()
            self.sheet1 = Ws()

    monkeypatch.setattr("agentzero.google.sync.load_credentials", lambda **k: object())
    monkeypatch.setattr("agentzero.google.sync.authorize_gspread", lambda c: type("Client", (), {"open_by_key": lambda self, k: Sp()})())
    monkeypatch.setattr("agentzero.google.client.open_spreadsheet", lambda c, sid: Sp())

    kept, deleted, title = prune_db_to_sheet(db=db, settings=_settings(tmp_path))
    assert deleted == 1
    assert kept == 1
    assert title == "AgentZero - 2026 Job Search"
    assert db.get_job(extra.job_id) is None
    assert db.get_job(on_sheet.job_id) is not None
    db.close()


def test_plan_prune_requires_sheet_id(tmp_path):
    db = Database(tmp_path / "jobs.db")
    settings = Settings(_env_file=None, sheet_id=None)
    with pytest.raises(ValueError, match="SHEET_ID"):
        plan_prune_db_to_sheet(db=db, settings=settings)
    db.close()

