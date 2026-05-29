"""Google Sheets sync for the job tracker spreadsheet."""

from __future__ import annotations

from typing import Any, Protocol

from agentzero.storage.csv_export import EXPORT_COLUMNS, job_to_row
from agentzero.storage.db import Database


class SheetsClient(Protocol):
    def open_by_key(self, key: str) -> Any: ...


class SheetsSync:
    """Upsert job rows to a Google Sheet by ``job_id``."""

    def __init__(self, client: SheetsClient, sheet_id: str) -> None:
        self._client = client
        self._sheet_id = sheet_id
        self._worksheet: Any | None = None

    @property
    def worksheet(self) -> Any:
        if self._worksheet is None:
            spreadsheet = self._client.open_by_key(self._sheet_id)
            self._worksheet = spreadsheet.sheet1
        return self._worksheet

    def sync(self, db: Database) -> int:
        jobs = db.list_jobs()
        rows = [job_to_row(job) for job in jobs]
        header = EXPORT_COLUMNS
        values = [header] + [[row.get(col, "") for col in header] for row in rows]
        self.worksheet.clear()
        self.worksheet.update("A1", values)
        return len(rows)
