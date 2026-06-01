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
