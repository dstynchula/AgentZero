"""Tests for browser session cookie import and storage paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentzero.config import Settings
from agentzero.scrape.browser_session import (
    import_cookies_file,
    load_storage_state,
    normalize_cookies,
    parse_cookie_import,
    storage_state_path,
)


def test_storage_state_path_per_site():
    s = Settings(_env_file=None, scrape_storage_state_dir=Path("data/browser_storage_state"))
    assert storage_state_path(s, "glassdoor") == Path("data/browser_storage_state/glassdoor.json")


def test_normalize_cookies_cookie_editor_format():
    raw = [
        {
            "domain": ".glassdoor.com",
            "name": "session",
            "value": "abc",
            "path": "/",
            "expirationDate": 9999999999,
            "httpOnly": True,
            "secure": True,
            "sameSite": "lax",
        }
    ]
    cookies = normalize_cookies(raw)
    assert len(cookies) == 1
    assert cookies[0]["name"] == "session"
    assert cookies[0]["sameSite"] == "Lax"
    assert cookies[0]["expires"] == 9999999999


def test_parse_cookie_import_storage_state():
    payload = {"cookies": [{"name": "a", "value": "1", "domain": ".x.com", "path": "/"}], "origins": []}
    state = parse_cookie_import(payload)
    assert len(state["cookies"]) == 1


def test_parse_cookie_import_bare_array():
    payload = [{"name": "a", "value": "1", "domain": ".x.com", "path": "/"}]
    state = parse_cookie_import(payload)
    assert len(state["cookies"]) == 1


def test_parse_cookie_import_invalid():
    with pytest.raises(ValueError, match="Expected Playwright"):
        parse_cookie_import({"foo": "bar"})


def test_import_cookies_file_roundtrip(tmp_path):
    source = tmp_path / "export.json"
    source.write_text(
        json.dumps([{"domain": ".linkedin.com", "name": "li", "value": "v", "path": "/"}]),
        encoding="utf-8",
    )
    dest = tmp_path / "state.json"
    count = import_cookies_file(source, dest)
    assert count == 1
    loaded = load_storage_state(dest)
    assert loaded is not None
    assert loaded["cookies"][0]["domain"] == ".linkedin.com"

from unittest.mock import MagicMock

from agentzero.scrape.browser_session import (
    SESSION_EXIT_CODES,
    SessionState,
    _site_page_helpers,
    apply_storage_state,
    classify_session,
    save_storage_state,
    session_status_message,
)


def test_site_page_helpers_indeed_and_unsupported():
    helpers = _site_page_helpers("indeed")
    assert len(helpers) == 4
    with pytest.raises(ValueError, match="Unsupported site"):
        _site_page_helpers("monster")


def test_normalize_cookies_skips_invalid_and_expires_variants():
    raw = [
        "not-a-dict",
        {"name": "x", "value": "1"},
        {"name": "ok", "value": "v", "domain": ".x.com", "expires": 1.5, "sameSite": True},
        {"name": "bad-ss", "value": "v", "domain": ".x.com", "sameSite": "weird"},
    ]
    cookies = normalize_cookies(raw)
    assert len(cookies) == 2
    assert cookies[0]["expires"] == 1.5
    assert cookies[0]["sameSite"] == "Strict"


def test_load_storage_state_missing(tmp_path):
    assert load_storage_state(tmp_path / "missing.json") is None


def test_save_and_apply_storage_state(tmp_path):
    dest = tmp_path / "nested" / "state.json"
    state = {"cookies": [{"name": "a", "value": "1", "domain": ".x.com", "path": "/"}], "origins": []}
    save_storage_state(dest, state)
    assert dest.is_file()
    ctx = MagicMock()
    apply_storage_state(ctx, state)
    ctx.add_cookies.assert_called_once()


def test_apply_storage_state_empty_cookies():
    ctx = MagicMock()
    apply_storage_state(ctx, {"cookies": [], "origins": []})
    ctx.add_cookies.assert_not_called()


def test_session_status_messages():
    assert "ready" in session_status_message("indeed", SessionState.READY)
    assert "login_job_boards" in session_status_message("indeed", SessionState.LOGIN_REQUIRED)
    assert "CAPTCHA" in session_status_message("indeed", SessionState.BLOCKED)
    assert "unknown" in session_status_message("indeed", SessionState.UNKNOWN).lower()


def test_session_exit_codes_complete():
    for state in SessionState:
        assert SESSION_EXIT_CODES[state] in (0, 1, 2, 3)


def test_classify_session_indeed_login_and_unknown():
    assert classify_session("indeed", "<html>Sign in to continue</html>", "https://secure.indeed.com/account/login") == SessionState.LOGIN_REQUIRED
    assert classify_session("indeed", "<html>empty page</html>", "https://www.indeed.com/jobs") == SessionState.UNKNOWN

