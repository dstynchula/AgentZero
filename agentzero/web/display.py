"""Table display helpers: truncation and column sorting."""

from __future__ import annotations

from dataclasses import dataclass

from agentzero.storage.csv_export import TRACKER_UI_COLUMNS as UI_COLUMNS

DEFAULT_SORT_COLUMN = "match_score"
DEFAULT_SORT_ORDER = "desc"

TABLE_TRUNCATE_LIMITS: dict[str, int] = {
    "notes": 80,
    "url": 80,
    "title": 120,
    "company": 80,
    "location": 64,
}
DEFAULT_TRUNCATE_LIMIT = 32

NUMERIC_SORT_COLUMNS = frozenset(
    {
        "comp_min",
        "comp_max",
        "glassdoor_rating",
        "match_score",
    }
)


@dataclass(frozen=True, slots=True)
class TruncatedCell:
    text: str
    full: str
    truncated: bool


def truncate_display(value: object, max_len: int) -> TruncatedCell:
    """Shorten *value* for table cells; preserve full string for tooltips."""
    full = "" if value is None else str(value)
    if len(full) <= max_len:
        return TruncatedCell(text=full, full=full, truncated=False)
    return TruncatedCell(text=full[: max_len - 1] + "…", full=full, truncated=True)


def truncate_limit_for_column(column: str) -> int:
    return TABLE_TRUNCATE_LIMITS.get(column, DEFAULT_TRUNCATE_LIMIT)


def truncate_row_for_table(row: dict[str, object]) -> dict[str, TruncatedCell]:
    return {
        column: truncate_display(row.get(column), truncate_limit_for_column(column))
        for column in UI_COLUMNS
    }


def parse_sort_params(
    sort: str | None,
    order: str | None,
    *,
    allowed_columns: tuple[str, ...] = UI_COLUMNS,
) -> tuple[str, bool]:
    """Return ``(column, descending)``; invalid values fall back to defaults."""
    column = (sort or "").strip() or DEFAULT_SORT_COLUMN
    if column not in allowed_columns:
        column = DEFAULT_SORT_COLUMN
    order_norm = (order or DEFAULT_SORT_ORDER).strip().lower()
    descending = order_norm != "asc"
    return column, descending


def _numeric_sort_key(row: dict[str, object], column: str, *, descending: bool) -> tuple:
    value = row.get(column)
    if value is None or value == "":
        return (1, 0.0)
    number = float(value)
    return (0, -number if descending else number)


def sort_job_rows(
    rows: list[dict[str, object]],
    column: str,
    *,
    descending: bool = True,
) -> list[dict[str, object]]:
    """Sort tracker-shaped rows by *column*."""
    if column not in UI_COLUMNS:
        column = DEFAULT_SORT_COLUMN
    if column in NUMERIC_SORT_COLUMNS:
        return sorted(
            rows,
            key=lambda row: _numeric_sort_key(row, column, descending=descending),
        )
    return sorted(
        rows,
        key=lambda row: str(row.get(column) or "").casefold(),
        reverse=descending,
    )


def build_list_query(
    *,
    show_rejected: bool = False,
    sort: str | None = None,
    order: str | None = None,
) -> str:
    """Query string for list index and back links (leading ``?`` when non-empty)."""
    parts: list[str] = []
    if show_rejected:
        parts.append("show_rejected=1")
    sort_column, descending = parse_sort_params(sort, order)
    parts.append(f"sort={sort_column}")
    parts.append(f"order={'desc' if descending else 'asc'}")
    if not parts:
        return ""
    return "?" + "&".join(parts)


def sort_link_for_column(
    column: str,
    *,
    current_sort: str,
    current_descending: bool,
    show_rejected: bool,
) -> str:
    """Relative query string for sorting by *column* (toggle order when active)."""
    if column == current_sort and current_descending:
        next_order = "asc"
    else:
        next_order = "desc"
    return build_list_query(show_rejected=show_rejected, sort=column, order=next_order)
