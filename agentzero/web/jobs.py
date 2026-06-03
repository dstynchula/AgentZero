"""Read helpers for the operator web UI."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class JobListFilters:
    company: str | None = None
    title: str | None = None
    status: str | None = None
    min_score: float | None = None
    min_comp: float | None = None
    max_comp: float | None = None

    @classmethod
    def from_query(
        cls,
        *,
        company: str | None = None,
        title: str | None = None,
        status: str | None = None,
        min_score: str | None = None,
        min_comp: str | None = None,
        max_comp: str | None = None,
    ) -> JobListFilters:
        def _float(value: str | None) -> float | None:
            if value is None or not str(value).strip():
                return None
            try:
                return float(str(value).strip())
            except ValueError:
                return None

        return cls(
            company=(company or "").strip() or None,
            title=(title or "").strip() or None,
            status=(status or "").strip() or None,
            min_score=_float(min_score),
            min_comp=_float(min_comp),
            max_comp=_float(max_comp),
        )

    def matches(self, row: dict[str, object]) -> bool:
        if self.company:
            needle = self.company.casefold()
            if needle not in str(row.get("company") or "").casefold():
                return False
        if self.title:
            needle = self.title.casefold()
            if needle not in str(row.get("title") or "").casefold():
                return False
        if self.status:
            if str(row.get("status") or "") != self.status:
                return False
        score = row.get("match_score")
        if self.min_score is not None:
            if score is None or float(score) < self.min_score:
                return False
        comp_max = row.get("comp_max")
        comp_min = row.get("comp_min")
        effective_max = comp_max if comp_max is not None else comp_min
        if self.min_comp is not None:
            if effective_max is None or float(effective_max) < self.min_comp:
                return False
        effective_min = comp_min if comp_min is not None else comp_max
        if self.max_comp is not None:
            if effective_min is None or float(effective_min) > self.max_comp:
                return False
        return True

    def query_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        if self.company:
            items.append(("company", self.company))
        if self.title:
            items.append(("title", self.title))
        if self.status:
            items.append(("status", self.status))
        if self.min_score is not None:
            items.append(("min_score", str(self.min_score)))
        if self.min_comp is not None:
            items.append(("min_comp", str(self.min_comp)))
        if self.max_comp is not None:
            items.append(("max_comp", str(self.max_comp)))
        return items


def list_jobs_for_ui(
    db: Database,
    *,
    include_rejected: bool = False,
    status_filter: str | None = None,
    filters: JobListFilters | None = None,
    sort: str | None = None,
    order: str | None = None,
) -> list[dict[str, object]]:
    """Return tracker-shaped rows for jobs, hiding rejected unless requested."""
    active_filters = filters or JobListFilters()
    status = status_filter or active_filters.status
    rows: list[dict[str, object]] = []
    for job in db.list_jobs():
        if not include_rejected and job.status == ApplicationStatus.REJECTED:
            continue
        if status is not None and job.status.value != status:
            continue
        row = job_to_tracker_ui_row(job)
        if not active_filters.matches(row):
            continue
        rows.append(row)
    sort_column, descending = parse_sort_params(sort, order)
    return sort_job_rows(rows, sort_column, descending=descending)


def jobs_for_table(
    db: Database,
    *,
    include_rejected: bool = False,
    filters: JobListFilters | None = None,
    sort: str | None = None,
    order: str | None = None,
) -> list[dict[str, Any]]:
    """Rows for the index template: full data plus truncated display cells."""
    rows = list_jobs_for_ui(
        db,
        include_rejected=include_rejected,
        filters=filters,
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
    """Full job payload for the detail card (``job_to_row`` plus description)."""
    job = db.get_job(job_id)
    if job is None:
        return None
    row = job_to_row(job)
    row["description"] = job.description or ""
    return row


def list_context(
    *,
    show_rejected: bool = False,
    filters: JobListFilters | None = None,
    sort: str | None = None,
    order: str | None = None,
) -> dict[str, object]:
    """Shared index template context for sort links and query preservation."""
    active_filters = filters or JobListFilters()
    sort_column, descending = parse_sort_params(sort, order)
    return {
        "sort": sort_column,
        "order": "desc" if descending else "asc",
        "sort_descending": descending,
        "filters": active_filters,
        "list_query": build_list_query(
            show_rejected=show_rejected,
            sort=sort_column,
            order="desc" if descending else "asc",
            filters=active_filters,
        ),
        "sort_links": {
            column: sort_link_for_column(
                column,
                current_sort=sort_column,
                current_descending=descending,
                show_rejected=show_rejected,
                filters=active_filters,
            )
            for column in UI_COLUMNS
        },
    }


__all__ = [
    "DEFAULT_SORT_COLUMN",
    "DEFAULT_SORT_ORDER",
    "JobListFilters",
    "LIST_VIEW_DEFAULT_COLUMNS",
    "UI_COLUMNS",
    "job_detail_for_ui",
    "jobs_for_table",
    "list_context",
    "list_jobs_for_ui",
]
