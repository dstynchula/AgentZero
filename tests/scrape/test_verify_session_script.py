"""Tests for verify_browser_session script (mocked probe)."""

from __future__ import annotations

import sys
from unittest.mock import patch

from agentzero.scrape.browser_session import SessionState
from agentzero.scrape.session_probe import SessionProbeResult


def _run_verify(probe_return):
    with patch("agentzero.scrape.session_probe.probe_browser_session", return_value=probe_return):
        with patch.object(sys, "argv", ["verify_browser_session.py", "--site", "glassdoor"]):
            from scripts.verify_browser_session import main

            return main()


def test_verify_main_ready_exit_code():
    ready = SessionProbeResult(site="glassdoor", state=SessionState.READY, url="https://x.com", listing_count=3)
    assert _run_verify(ready) == 0


def test_verify_main_login_required():
    need = SessionProbeResult(
        site="glassdoor",
        state=SessionState.LOGIN_REQUIRED,
        url="https://glassdoor.com/login",
    )
    assert _run_verify(need) == 1


def test_verify_main_blocked():
    blocked = SessionProbeResult(
        site="glassdoor",
        state=SessionState.BLOCKED,
        url="https://glassdoor.com/jobs",
    )
    assert _run_verify(blocked) == 2


def test_verify_main_error():
    err = SessionProbeResult(site="glassdoor", state=SessionState.UNKNOWN, url="", error="boom")
    assert _run_verify(err) == 3
