from agentzero.google.sheets import SheetsSync
from agentzero.models import JobPosting
from agentzero.storage.csv_export import SHEET_COLUMNS
from agentzero.storage.db import Database


class FakeWorksheet:
    def __init__(self) -> None:
        self.cells: list = []
        self.cleared = False

    def get_all_values(self) -> list:
        return self.cells

    def clear(self) -> None:
        self.cleared = True

    def update(self, _range: str, values: list) -> None:
        self.cells = values


class FakeSpreadsheet:
    def __init__(self) -> None:
        self.sheet1 = FakeWorksheet()


class FakeClient:
    def __init__(self) -> None:
        self.spreadsheet = FakeSpreadsheet()

    def open_by_key(self, key: str) -> FakeSpreadsheet:
        return self.spreadsheet


def test_sheets_sync_upserts_rows(tmp_path):
    db = Database(tmp_path / "jobs.db")
    db.upsert_job(
        JobPosting(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    )
    client = FakeClient()
    sync = SheetsSync(client, "sheet-id-123")
    count, import_result = sync.sync(db)
    assert count == 1
    assert import_result.updated == 0
    assert client.spreadsheet.sheet1.cleared
    assert client.spreadsheet.sheet1.cells[0] == SHEET_COLUMNS
    assert len(client.spreadsheet.sheet1.cells[0]) == 13
    db.close()


def test_sheets_sync_respects_min_match_score(tmp_path):
    db = Database(tmp_path / "jobs.db")
    db.upsert_job(
        JobPosting(
            title="Security Engineer",
            company="GoodCo",
            url="https://x.com/good",
            source="indeed",
            match_score=0.9,
        )
    )
    db.upsert_job(
        JobPosting(
            title="Director Physical Security",
            company="OtherCo",
            url="https://x.com/low",
            source="glassdoor",
            match_score=0.25,
        )
    )
    sync = SheetsSync(FakeClient(), "sheet-id")
    count, _ = sync.sync(db, import_user_fields=False, min_match_score=0.75)
    assert count == 1
    assert sync.worksheet.cells[1][2] == "Security Engineer"
    db.close()
