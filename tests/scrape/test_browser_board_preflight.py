"""Tests for scrape session preflight on browser boards."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agentzero.config import Settings
from agentzero.scrape.browser_board import BrowserJobBoardSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_preflight_skips_fetch_on_login_wall(tmp_path):
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "indeed_browser_profile",
        scrape_session_preflight=True,
        search_terms=["Engineer"],
        locations=["Remote"],
        results_wanted=5,
    )
    source = BrowserJobBoardSource(settings, site="glassdoor")

    mock_page = MagicMock()
    mock_page.url = "https://www.glassdoor.com/profile/login_input.htm"
    mock_page.content.return_value = _read("glassdoor_login.html")

    mock_context = MagicMock()
    mock_pw = MagicMock()

    with patch(
        "agentzero.scrape.browser_board.launch_browser_page",
        return_value=(mock_pw, mock_context, mock_page, None),
    ), patch(
        "playwright.sync_api.sync_playwright",
        return_value=MagicMock(
            __enter__=MagicMock(return_value=mock_pw),
            __exit__=MagicMock(return_value=False),
        ),
    ), patch(
        "agentzero.scrape.browser_board.close_browser_session",
    ), patch(
        "agentzero.scrape.browser_board.validate_browser_page_url",
        return_value=True,
    ):
        records = list(source.fetch())

    assert records == []
    mock_page.goto.assert_called_once()
