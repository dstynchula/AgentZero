"""Google Sheets sync for the job tracker spreadsheet."""

from __future__ import annotations

from typing import Any, Protocol

from agentzero.apply.tracking import import_tracker_rows, rows_from_sheet_values
from agentzero.google.sheet_import import SheetImportResult
from agentzero.storage.csv_export import SHEET_COLUMNS, job_to_sheet_row
from agentzero.storage.db import Database


class SheetsClient(Protocol):
    def open_by_key(self, key: str) -> Any: ...


class SheetsSync:
    """Push SQLite jobs to a Google Sheet; import user-edited columns before each write."""

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

    def read_tracker_rows(self) -> list[dict[str, str]]:
        """Read all sheet rows as column dicts."""
        return rows_from_sheet_values(self.worksheet.get_all_values())

    def read_rows_by_job_id(self) -> dict[str, dict[str, str]]:
        """Read user-editable columns keyed by ``job_id`` (legacy helper)."""
        from agentzero.apply.sheet_fields import SHEET_USER_COLUMNS

        out: dict[str, dict[str, str]] = {}
        for row in self.read_tracker_rows():
            job_id = str(row.get("job_id") or "").strip()
            if not job_id:
                continue
            out[job_id] = {column: row.get(column, "") for column in SHEET_USER_COLUMNS}
        return out

    def import_user_fields(
        self,
        db: Database,
        *,
        search_terms: list[str] | None = None,
    ) -> SheetImportResult:
        """Load tracker rows into SQLite (updates, new applied jobs, sheet edits)."""
        result = import_tracker_rows(db, self.read_tracker_rows(), search_terms=search_terms)
        return SheetImportResult(
            updated=result.updated,
            created=result.created,
            skipped_unknown_job_id=result.skipped,
            rows_read=result.rows_read,
        )

    def sync(
        self,
        db: Database,
        *,
        import_user_fields: bool = True,
        search_terms: list[str] | None = None,
        min_match_score: float | None = None,
    ) -> tuple[int, SheetImportResult]:
        import_result = SheetImportResult()
        if import_user_fields:
            import_result = self.import_user_fields(db, search_terms=search_terms)

        jobs = db.list_jobs()
        jobs = sorted(
            jobs,
            key=lambda j: (j.match_score is None, -(j.match_score or 0.0)),
        )
        from agentzero.rank.export_filter import filter_jobs_for_export

        jobs, _below_floor = filter_jobs_for_export(jobs, min_match_score)
        rows = [job_to_sheet_row(job) for job in jobs]
        header = SHEET_COLUMNS
        values = [header] + [[row.get(col, "") for col in header] for row in rows]
        self.worksheet.clear()
        self.worksheet.update("A1", values)
        return len(rows), import_result

    def read_job_ids(self) -> set[str]:
        """Return ``job_id`` values from the sheet (header row + ``job_id`` column)."""
        rows = self.worksheet.get_all_values()
        if not rows:
            return set()
        header = rows[0]
        try:
            col = header.index("job_id")
        except ValueError as exc:
            raise ValueError("Sheet is missing a job_id column") from exc
        ids: set[str] = set()
        for row in rows[1:]:
            if col < len(row):
                value = row[col].strip()
                if value:
                    ids.add(value)
        return ids
