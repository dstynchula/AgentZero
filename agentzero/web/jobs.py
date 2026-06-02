"""Read helpers for the operator web UI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentzero.models import ApplicationStatus
from agentzero.storage.csv_export import TRACKER_UI_COLUMNS, job_to_row, job_to_tracker_ui_row
from agentzero.web.display import (
    DEFAULT_SORT_COLUMN,
    DEFAULT_SORT_ORDER,
    build_list_query,
    parse_sort_params,
    sort_job_rows,
    sort_link_for_column,
    truncate_row_for_table,
)

if TYPE_CHECKING:
    from agentzero.storage.db import Database

UI_COLUMNS = (*TRACKER_UI_COLUMNS,)

# Default list-view columns (column picker can enable the rest).
LIST_VIEW_DEFAULT_COLUMNS = (
    "source",
    "company",
    "title",
    "comp_max",
    "match_score",
    "status",
)


def list_jobs_for_ui(
    db: Database,
    *,
    include_rejected: bool = False,
    status_filter: str | None = None,
    sort: str | None = None,
    order: str | None = None,
) -> list[dict[str, object]]:
    """Return tracker-shaped rows for jobs, hiding rejected unless requested."""
    rows: list[dict[str, object]] = []
    for job in db.list_jobs():
        if not include_rejected and job.status == ApplicationStatus.REJECTED:
            continue
        if status_filter is not None and job.status.value != status_filter:
            continue
        rows.append(job_to_tracker_ui_row(job))
    sort_column, descending = parse_sort_params(sort, order)
    return sort_job_rows(rows, sort_column, descending=descending)


def jobs_for_table(
    db: Database,
    *,
    include_rejected: bool = False,
    sort: str | None = None,
    order: str | None = None,
) -> list[dict[str, Any]]:
    """Rows for the index template: full data plus truncated display cells."""
    rows = list_jobs_for_ui(
        db,
        include_rejected=include_rejected,
        sort=sort,
        order=order,
    )
    return [
        {
            "data": row,
            "cells": truncate_row_for_table(row),
            "job_id": row["job_id"],
        }
        for row in rows
    ]


def job_detail_for_ui(db: Database, job_id: str) -> dict[str, object] | None:
    """Full job payload for the detail card (``job_to_row`` schema)."""
    job = db.get_job(job_id)
    if job is None:
        return None
    return job_to_row(job)


def list_context(
    *,
    show_rejected: bool = False,
    sort: str | None = None,
    order: str | None = None,
) -> dict[str, object]:
    """Shared index template context for sort links and query preservation."""
    sort_column, descending = parse_sort_params(sort, order)
    return {
        "sort": sort_column,
        "order": "desc" if descending else "asc",
        "sort_descending": descending,
        "list_query": build_list_query(
            show_rejected=show_rejected,
            sort=sort_column,
            order="desc" if descending else "asc",
        ),
        "sort_links": {
            column: sort_link_for_column(
                column,
                current_sort=sort_column,
                current_descending=descending,
                show_rejected=show_rejected,
            )
            for column in UI_COLUMNS
        },
    }


__all__ = [
    "DEFAULT_SORT_COLUMN",
    "DEFAULT_SORT_ORDER",
    "LIST_VIEW_DEFAULT_COLUMNS",
    "UI_COLUMNS",
    "job_detail_for_ui",
    "jobs_for_table",
    "list_context",
    "list_jobs_for_ui",
]
