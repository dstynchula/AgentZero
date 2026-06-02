"""Redact secrets and credential-like strings from logs and printed output."""

from __future__ import annotations

import logging
import re

# OpenAI / Anthropic API keys
_SK_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_SK_ANT = re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}\b")
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_AUTH_HEADER = re.compile(
    r"(Authorization:\s*)([^\s,]+)",
    re.IGNORECASE,
)
_JSON_SECRET_FIELDS = re.compile(
    r'("(?:client_secret|refresh_token|access_token|private_key)"\s*:\s*)"[^"]*"',
    re.IGNORECASE,
)
_PROXY_CREDS = re.compile(r"(https?://)[^/\s:@]+:[^@\s/]+@")
_REDACTED = "***REDACTED***"

_INSTALLED = False


def redact_secrets(text: str) -> str:
    """Return *text* with common secret patterns replaced."""
    if not text:
        return text
    out = text
    out = _SK_ANT.sub(_REDACTED, out)
    out = _SK_KEY.sub(_REDACTED, out)
    out = _BEARER.sub(f"Bearer {_REDACTED}", out)
    out = _AUTH_HEADER.sub(rf"\1{_REDACTED}", out)
    out = _JSON_SECRET_FIELDS.sub(rf'\1"{_REDACTED}"', out)
    out = _PROXY_CREDS.sub(rf"\1{_REDACTED}@", out)
    return out


class SecretRedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from messages and tracebacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            record.args = tuple(
                redact_secrets(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)
        return True


def install_log_redaction() -> None:
    """Attach secret redaction to the root logger (idempotent)."""
    global _INSTALLED
    if _INSTALLED:
        return
    root = logging.getLogger()
    filt = SecretRedactingFilter()
    root.addFilter(filt)
    for handler in root.handlers:
        handler.addFilter(filt)
    _INSTALLED = True


def mask_sheet_id(sheet_id: str | None) -> str:
    """Mask a Google Sheet ID for operator logs."""
    if not sheet_id:
        return "(not set)"
    sid = sheet_id.strip()
    if len(sid) <= 8:
        return sid
    return f"{sid[:8]}…"
