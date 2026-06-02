"""Secret redaction for logs and operator output."""

from __future__ import annotations

import logging

from agentzero.log_redaction import (
    SecretRedactingFilter,
    install_log_redaction,
    mask_sheet_id,
    redact_secrets,
)


def test_redact_openai_key():
    text = "key=sk-abcdefghijklmnopqrstuvwxyz1234567890"
    out = redact_secrets(text)
    assert "sk-abc" not in out
    assert "***REDACTED***" in out


def test_redact_anthropic_key():
    text = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
    out = redact_secrets(text)
    assert "sk-ant" not in out


def test_redact_bearer_token():
    out = redact_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.x")
    assert "eyJhbG" not in out


def test_redact_json_client_secret():
    raw = '{"client_secret": "s3cret-value", "other": 1}'
    out = redact_secrets(raw)
    assert "s3cret-value" not in out


def test_redact_proxy_credentials():
    out = redact_secrets("proxy http://user:pass@proxy.example:8080/path")
    assert "user:pass" not in out


def test_innocent_text_unchanged():
    text = "Indeed browser fetch failed: timeout"
    assert redact_secrets(text) == text


def test_mask_sheet_id():
    assert mask_sheet_id("abcdefghijklmnop") == "abcdefgh…"
    assert mask_sheet_id(None) == "(not set)"


def test_logging_filter_redacts_message():
    install_log_redaction()
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="failed with sk-abcdefghijklmnopqrstuvwxyz",
        args=(),
        exc_info=None,
    )
    SecretRedactingFilter().filter(record)
    assert "sk-abc" not in record.msg
