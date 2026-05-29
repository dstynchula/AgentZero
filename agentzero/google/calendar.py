"""Google Calendar helpers for interview reminders."""

from __future__ import annotations

from typing import Any


def create_event(
    service: Any,
    *,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
) -> dict:
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": "UTC"},
        "end": {"dateTime": end_iso, "timeZone": "UTC"},
    }
    return service.events().insert(calendarId="primary", body=body).execute()
