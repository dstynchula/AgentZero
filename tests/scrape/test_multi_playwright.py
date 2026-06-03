"""Tests for shared Playwright lifecycle across multi-board scrapes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentzero.config import Settings
from agentzero.scrape.browser_board import BrowserJobBoardSource
from agentzero.scrape.multi import MultiSource


def _sync_playwright_cm(mock_pw: MagicMock | None = None) -> tuple[MagicMock, MagicMock]:
    pw = mock_pw or MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=pw)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, pw


def test_multi_source_reuses_single_playwright(tmp_path):
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Engineer"],
        locations=["Remote"],
        scrape_session_preflight=False,
        scrape_browser_headless=True,
    )
    sources = [
        BrowserJobBoardSource(settings, site="indeed"),
        BrowserJobBoardSource(settings, site="linkedin"),
        BrowserJobBoardSource(settings, site="glassdoor"),
    ]
    multi = MultiSource(sources)
    mock_page = MagicMock()
    mock_page.url = "https://example.com/jobs"
    mock_page.content.return_value = "<html></html>"
    cm, shared_pw = _sync_playwright_cm()

    with (
        patch("playwright.sync_api.sync_playwright", return_value=cm) as sync_pw,
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            return_value=(shared_pw, MagicMock(), mock_page, None),
        ) as launch,
        patch("agentzero.scrape.browser_board.close_browser_session"),
        patch("agentzero.scrape.browser_board.validate_browser_page_url", return_value=True),
        patch("agentzero.scrape.browser_board.wait_for_html", return_value="<html></html>"),
        patch("agentzero.scrape.browser_board.maybe_wait_for_human"),
        patch("agentzero.scrape.browser_board.click_consent_buttons"),
        patch("agentzero.scrape.browser_indeed._dismiss_indeed_consent"),
    ):
        multi.fetch()

    sync_pw.assert_called_once()
    assert launch.call_count == 3
    for call in launch.call_args_list:
        assert call.kwargs.get("playwright") is shared_pw


def test_close_browser_session_cdp_does_not_stop_shared_playwright(tmp_path):
    from agentzero.scrape.browser_common import close_browser_session

    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        scrape_cdp_url="http://host.docker.internal:9222",
        scrape_cdp_sites=["glassdoor"],
        cdp_allow_docker_host=True,
    )
    playwright = MagicMock()
    browser = MagicMock()
    context = MagicMock()

    close_browser_session(
        playwright,
        context,
        settings,
        site="glassdoor",
        browser=browser,
        stop_playwright=False,
    )

    browser.close.assert_called_once()
    playwright.stop.assert_not_called()

    playwright.reset_mock()
    browser.reset_mock()
    close_browser_session(
        playwright,
        context,
        settings,
        site="glassdoor",
        browser=browser,
        stop_playwright=True,
    )
    browser.close.assert_called_once()
    playwright.stop.assert_called_once()
