from agentzero.google.sheets import SheetsSync
from agentzero.models import JobPosting
from agentzero.storage.db import Database


class FakeWorksheet:
    def __init__(self) -> None:
        self.cells: list = []
        self.cleared = False

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
    count = sync.sync(db)
    assert count == 1
    assert client.spreadsheet.sheet1.cleared
    assert client.spreadsheet.sheet1.cells[0][0] == "source"
    db.close()
