"""Import human-edited tracker fields from Google Sheets into SQLite."""

from __future__ import annotations

from dataclasses import dataclass

from agentzero.apply.sheet_fields import (
    SHEET_USER_COLUMNS,
    merge_user_fields_from_sheet,
    parse_sheet_date,
    parse_sheet_status,
)
from agentzero.storage.db import Database

__all__ = (
    "SHEET_USER_COLUMNS",
    "SheetImportResult",
    "import_user_fields_to_db",
    "merge_user_fields_from_sheet",
    "parse_sheet_date",
    "parse_sheet_status",
)


@dataclass(frozen=True, slots=True)
class SheetImportResult:
    updated: int = 0
    created: int = 0
    skipped_unknown_job_id: int = 0
    rows_read: int = 0


def import_user_fields_to_db(db: Database, rows_by_job_id: dict[str, dict[str, str]]) -> SheetImportResult:
    """Merge sheet user columns into SQLite jobs matched by ``job_id``."""
    updated = 0
    skipped = 0

    for job_id, row in rows_by_job_id.items():
        job = db.get_job(job_id)
        if job is None:
            skipped += 1
            continue
        merged, changed = merge_user_fields_from_sheet(job, row)
        if changed:
            db.upsert_job(merged)
            updated += 1

    return SheetImportResult(
        updated=updated,
        skipped_unknown_job_id=skipped,
        rows_read=len(rows_by_job_id),
    )
