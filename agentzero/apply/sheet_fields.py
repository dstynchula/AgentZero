"""Parse and merge human-edited tracker columns from sheet rows."""

from __future__ import annotations

import re
from datetime import date, datetime

from agentzero.models import ApplicationStatus, JobPosting

SHEET_USER_COLUMNS = (
    "status",
    "date_first_contacted",
    "date_applied",
    "notes",
)

# Statuses that auto-promote to APPLIED when the sheet carries date_applied (no explicit status).
PRE_APPLICATION_STATUSES = frozenset(
    {
        ApplicationStatus.LEAD,
        ApplicationStatus.NEW,
        ApplicationStatus.REVIEWED,
        ApplicationStatus.QUEUED,
        ApplicationStatus.CONTACTED,
    }
)


def parse_sheet_date(value: object) -> date | None:
    """Parse common sheet date strings (ISO, US slash, datetime prefix)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass

    if "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            pass

    slash = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", text)
    if slash:
        month, day, year = int(slash.group(1)), int(slash.group(2)), int(slash.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None

    return None


def parse_sheet_status(value: object) -> ApplicationStatus | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return ApplicationStatus(text)
    except ValueError:
        return None


def merge_user_fields_from_sheet(job: JobPosting, row: dict[str, str]) -> tuple[JobPosting, bool]:
    """Apply non-empty user-edited sheet cells onto *job*. Returns (job, changed)."""
    updates: dict = {}

    date_applied = parse_sheet_date(row.get("date_applied"))
    if date_applied is not None:
        updates["date_applied"] = date_applied

    date_contacted = parse_sheet_date(row.get("date_first_contacted"))
    if date_contacted is not None:
        updates["date_first_contacted"] = date_contacted

    status = parse_sheet_status(row.get("status"))
    if status is not None:
        updates["status"] = status
    elif date_applied is not None and job.status in PRE_APPLICATION_STATUSES:
        updates["status"] = ApplicationStatus.APPLIED

    notes = str(row.get("notes") or "").strip()
    if notes:
        updates["notes"] = notes

    if not updates:
        return job, False

    updated = job.model_copy(update=updates)
    return updated, updated != job
