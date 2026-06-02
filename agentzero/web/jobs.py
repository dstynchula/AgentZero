"""Read helpers for the operator web UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentzero.models import ApplicationStatus
from agentzero.storage.csv_export import SHEET_COLUMNS, job_to_sheet_row

if TYPE_CHECKING:
    from agentzero.storage.db import Database

UI_COLUMNS = (*SHEET_COLUMNS,)


def list_jobs_for_ui(
    db: Database,
    *,
    include_rejected: bool = False,
    status_filter: str | None = None,
) -> list[dict[str, object]]:
    """Return sheet-shaped rows for jobs, hiding rejected unless requested."""
    rows: list[dict[str, object]] = []
    for job in db.list_jobs():
        if not include_rejected and job.status == ApplicationStatus.REJECTED:
            continue
        if status_filter is not None and job.status.value != status_filter:
            continue
        rows.append(job_to_sheet_row(job))
    return rows
