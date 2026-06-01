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
