"""Gmail helpers for outreach tracking."""

from __future__ import annotations

from typing import Any


def send_message(service: Any, *, to: str, subject: str, body: str) -> dict:
    """Send a plain-text email via the Gmail API."""
    import base64
    from email.mime.text import MIMEText

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()
