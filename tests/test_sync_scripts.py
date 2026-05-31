"""Tests for sync_sheets and run_scrape CLI helpers."""

from __future__ import annotations

import pytest

from agentzero.config import Settings
from agentzero.google.sync import sync_jobs_to_sheet
from agentzero.models import JobPosting
from agentzero.storage.db import Database


class FakeWorksheet:
    def __init__(self) -> None:
        self.values: list = []

    def get_all_values(self) -> list:
        return self.values

    def clear(self) -> None:
        self.values = []

    def update(self, _range: str, values: list) -> None:
        self.values = values


class FakeSpreadsheet:
    def __init__(self) -> None:
        self.title = "AgentZero - 2026 Job Search"
        self.sheet1 = FakeWorksheet()


class FakeGspreadClient:
    def __init__(self) -> None:
        self.spreadsheet = FakeSpreadsheet()

    def open_by_key(self, key: str) -> FakeSpreadsheet:
        return self.spreadsheet


def test_sync_jobs_to_sheet_writes_rows(tmp_path, monkeypatch):
    db = Database(tmp_path / "jobs.db")
    db.upsert_job(
        JobPosting(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    )
    settings = Settings(
        _env_file=None,
        sheet_id="abc123",
        google_client_secret=tmp_path / "secret.json",
        google_token_path=tmp_path / "token.json",
    )
    settings.google_client_secret.write_text("{}", encoding="utf-8")
    settings.google_token_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "agentzero.google.sync.load_credentials",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "agentzero.google.sync.authorize_gspread",
        lambda creds: FakeGspreadClient(),
    )
    monkeypatch.setattr(
        "agentzero.google.client.open_spreadsheet",
        lambda creds, sheet_id: FakeSpreadsheet(),
    )

    result = sync_jobs_to_sheet(db=db, settings=settings)
    assert result.row_count == 1
    assert result.spreadsheet_title == "AgentZero - 2026 Job Search"


def test_sync_jobs_to_sheet_requires_sheet_id(tmp_path):
    db = Database(tmp_path / "jobs.db")
    settings = Settings(_env_file=None, sheet_id=None)
    with pytest.raises(ValueError, match="SHEET_ID"):
        sync_jobs_to_sheet(db=db, settings=settings)


def test_run_scrape_skip_ingest_without_snapshot(tmp_path, monkeypatch):
    import scripts.run_scrape as run_scrape_mod

    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume").mkdir()
    code = run_scrape_mod.run(
        limit=5,
        skip_resume_ingest=True,
        search_prompt=False,
        refresh_search=False,
    )
    assert code == 1
