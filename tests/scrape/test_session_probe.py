"""Tests for session probe SSRF guard after navigation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentzero.config import Settings
from agentzero.scrape.browser_session import SessionState
from agentzero.scrape.session_probe import probe_browser_session


def test_probe_browser_session_blocks_unsafe_post_navigation_url():
    settings = Settings(
        _env_file=None,
        search_terms=["engineer"],
        locations=["Remote"],
    )
    page = MagicMock()
    page.url = "http://127.0.0.1/internal"

    with (
        patch(
            "agentzero.scrape.browser_common.launch_browser_page",
            return_value=(None, None, page),
        ),
        patch("agentzero.scrape.browser_common.close_browser_session"),
        patch(
            "agentzero.scrape.browser_common.validate_browser_page_url",
            return_value=False,
        ),
    ):
        result = probe_browser_session(settings, "indeed")

    assert result.state is SessionState.UNKNOWN
    assert result.error == "blocked URL after navigation"
    assert result.url == "http://127.0.0.1/internal"

from agentzero.scrape.session_probe import SessionProbeResult


def test_session_probe_result_exit_codes():
    ready = SessionProbeResult(site="indeed", state=SessionState.READY, url="https://indeed.com")
    assert ready.exit_code == 0
    err = SessionProbeResult(site="indeed", state=SessionState.READY, url="", error="boom")
    assert err.exit_code == 3


def test_probe_browser_session_unknown_site():
    settings = Settings(_env_file=None, search_terms=["x"], locations=["Remote"])
    result = probe_browser_session(settings, "monster")
    assert result.state is SessionState.UNKNOWN
    assert result.error == "unknown site: monster"


def test_probe_browser_session_ready_with_listings():
    settings = Settings(_env_file=None, search_terms=["engineer"], locations=["Remote"])
    page = MagicMock()
    page.url = "https://www.indeed.com/jobs"
    html = "<div class='job_seen_beacon'>job</div>"

    with (
        patch("agentzero.scrape.browser_common.launch_browser_page", return_value=(None, None, page)),
        patch("agentzero.scrape.browser_common.close_browser_session"),
        patch("agentzero.scrape.browser_common.validate_browser_page_url", return_value=True),
        patch("agentzero.scrape.browser_common.wait_for_html", return_value=html),
        patch("agentzero.scrape.session_probe.classify_session", return_value=SessionState.READY),
    ):
        result = probe_browser_session(settings, "indeed")

    assert result.state is SessionState.READY
    assert result.listing_count >= 0
    assert result.error is None


def test_probe_browser_session_wait_for_html_fallback():
    settings = Settings(_env_file=None, search_terms=["engineer"], locations=["Remote"])
    page = MagicMock()
    page.url = "https://www.indeed.com/jobs"
    page.content.return_value = "<html>login</html>"

    with (
        patch("agentzero.scrape.browser_common.launch_browser_page", return_value=(None, None, page)),
        patch("agentzero.scrape.browser_common.close_browser_session"),
        patch("agentzero.scrape.browser_common.validate_browser_page_url", return_value=True),
        patch("agentzero.scrape.browser_common.wait_for_html", return_value=None),
        patch("agentzero.scrape.session_probe.classify_session", return_value=SessionState.LOGIN_REQUIRED),
    ):
        result = probe_browser_session(settings, "indeed")

    assert result.state is SessionState.LOGIN_REQUIRED
    page.content.assert_called_once()


def test_probe_browser_session_exception():
    settings = Settings(_env_file=None, search_terms=["engineer"], locations=["Remote"])
    with (
        patch(
            "agentzero.scrape.browser_common.launch_browser_page",
            side_effect=RuntimeError("browser down"),
        ),
        patch("agentzero.scrape.browser_common.close_browser_session"),
    ):
        result = probe_browser_session(settings, "indeed")

    assert result.state is SessionState.UNKNOWN
    assert "browser down" in (result.error or "")

