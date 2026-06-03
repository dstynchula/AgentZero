"""Tests for LinkedIn/Glassdoor browser parsers and three-board factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentzero.config import Settings
from agentzero.scrape.browser_board import SITE_CONFIGS, BrowserJobBoardSource, _default_input
from agentzero.scrape.browser_linkedin import (
    build_linkedin_search_url,
    page_has_job_results,
    parse_linkedin_search_html,
)
from agentzero.scrape.factory import CORE_BROWSER_SITES, build_scrape_source, describe_scrape_stack
from agentzero.scrape.location import parse_search_location
from agentzero.scrape.multi import MultiSource
from agentzero.scrape.validate import validate_raw

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _sync_playwright_cm(mock_pw: MagicMock | None = None) -> tuple[MagicMock, MagicMock]:
    pw = mock_pw or MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=pw)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, pw


def _launch_return(page: MagicMock) -> tuple[MagicMock, MagicMock, MagicMock, None]:
    return (MagicMock(), MagicMock(), page, None)


def test_parse_linkedin_search_html():
    html = (FIXTURES / "linkedin_search.html").read_text(encoding="utf-8")
    records = parse_linkedin_search_html(html)
    assert len(records) == 2
    assert records[0]["title"] == "Staff Security Engineer"
    assert records[0]["company"] == "Acme Corp"
    assert records[0]["remote"] is True


def test_parse_linkedin_search_spa_html():
    html = (FIXTURES / "linkedin_search_spa.html").read_text(encoding="utf-8")
    assert page_has_job_results(html)
    records = parse_linkedin_search_html(html)
    assert len(records) == 2
    garner = next(r for r in records if r["company"] == "Garner Health")
    assert garner["title"] == "Staff Security Engineer"
    assert garner["url"] == "https://www.linkedin.com/jobs/view/4328174567"
    assert garner["location"] == "United States (Remote)"
    assert garner["remote"] is True
    assert garner["comp_raw"] == "$239K/yr - $275K/yr"
    principal = next(r for r in records if r["company"] == "Acme Corp")
    assert principal["title"] == "Principal Security Engineer"
    assert principal["url"].endswith("9876543210")


def test_parse_linkedin_search_embedded_only_html():
    html = (FIXTURES / "linkedin_search_embedded_only.html").read_text(encoding="utf-8")
    records = parse_linkedin_search_html(html)
    assert len(records) == 3
    by_company = {r["company"]: r for r in records}
    assert by_company["Rippling"]["title"] == "Lead Security Engineer"
    assert by_company["Rippling"]["location"] == "United States (Remote)"

    rippling_raw = by_company["Rippling"]
    assert rippling_raw.get("comp_raw") == "$200K/yr - $240K/yr"
    rippling = validate_raw(rippling_raw, source="linkedin").job
    assert rippling is not None
    assert rippling.comp_min == 200_000
    assert rippling.comp_max is not None
    assert rippling.comp_max >= rippling.comp_min
    assert by_company["EvenUp"]["title"] == "Lead Security Engineer"
    assert by_company["Harvey"]["title"] == "Staff Cloud Security Engineer"


def test_page_has_job_results_job_posting_marker():
    assert page_has_job_results('<script>"jobPosting:1234567890"</script>')


def test_build_linkedin_remote_url():
    parsed = parse_search_location("remote - usa")
    url = build_linkedin_search_url(term="Security Engineer", parsed=parsed)
    assert "keywords=Security" in url
    assert "f_WT=2" in url


def test_factory_three_board_stack():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=list(CORE_BROWSER_SITES),
        search_terms=["Staff Security Engineer", "Principal Security Engineer"],
        locations=["remote - usa"],
        remote_preferred=True,
        scrape_primary_query_only=True,
    )
    source = build_scrape_source(settings)
    assert isinstance(source, MultiSource)
    names = [s.name for s in source._sources]
    assert names == [
        "indeed_browser",
        "linkedin_browser",
        "glassdoor_browser",
    ]


def test_describe_scrape_stack():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed"],
        search_terms=["Security Engineer"],
        locations=["remote - usa"],
        remote_preferred=True,
    )
    source = build_scrape_source(settings)
    info = describe_scrape_stack(source, settings)
    assert info["primary_term"] == "Security Engineer"
    assert info["remote"] is True
    assert "indeed_browser" in info["sources"]


def test_site_configs_include_core_boards():
    assert set(SITE_CONFIGS) == {"indeed", "linkedin", "glassdoor"}


def test_browser_job_board_unsupported_site():
    settings = Settings(_env_file=None, search_terms=["x"], locations=["Remote"])
    with pytest.raises(ValueError, match="Unsupported browser site"):
        BrowserJobBoardSource(settings, site="monster")


def test_browser_job_board_name():
    settings = Settings(_env_file=None, search_terms=["x"], locations=["Remote"])
    assert BrowserJobBoardSource(settings, site="Indeed").name == "indeed_browser"


def test_browser_job_board_invalid_url_returns_empty(tmp_path):
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Engineer"],
        locations=["Remote"],
        scrape_session_preflight=False,
    )
    source = BrowserJobBoardSource(settings, site="linkedin")
    mock_page = MagicMock()
    mock_page.url = "https://evil.example/jobs"
    with (
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            return_value=_launch_return(mock_page),
        ),
        patch("playwright.sync_api.sync_playwright", return_value=_sync_playwright_cm()[0]),
        patch("agentzero.scrape.browser_board.close_browser_session"),
        patch(
            "agentzero.scrape.browser_board.validate_browser_page_url",
            return_value=False,
        ),
    ):
        assert source.fetch() == []


def test_browser_job_board_indeed_fetch_happy_path(tmp_path):
    html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Staff Security Engineer"],
        locations=["remote - usa"],
        remote_preferred=True,
        results_wanted=10,
        scrape_session_preflight=False,
        scrape_browser_headless=True,
        scrape_browser_pause_for_captcha=False,
    )
    source = BrowserJobBoardSource(settings, site="indeed")
    mock_page = MagicMock()
    mock_page.url = "https://www.indeed.com/jobs?q=staff"
    mock_page.content.return_value = html
    with (
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            return_value=_launch_return(mock_page),
        ),
        patch("playwright.sync_api.sync_playwright", return_value=_sync_playwright_cm()[0]),
        patch("agentzero.scrape.browser_board.close_browser_session"),
        patch(
            "agentzero.scrape.browser_board.validate_browser_page_url",
            return_value=True,
        ),
        patch("agentzero.scrape.browser_board.wait_for_html", return_value=html),
        patch("agentzero.scrape.browser_board.maybe_wait_for_human"),
        patch("agentzero.scrape.browser_indeed._dismiss_indeed_consent") as dismiss,
    ):
        records = list(source.fetch())
    dismiss.assert_called()
    assert len(records) == 2


def test_browser_job_board_glassdoor_uses_consent_buttons(tmp_path):
    html = (FIXTURES / "glassdoor_results.html").read_text(encoding="utf-8")
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Security Engineer"],
        locations=["Remote"],
        results_wanted=5,
        scrape_session_preflight=False,
        scrape_browser_headless=True,
    )
    source = BrowserJobBoardSource(settings, site="glassdoor")
    mock_page = MagicMock()
    mock_page.url = "https://www.glassdoor.com/Job/jobs.htm"
    mock_page.content.return_value = html
    with (
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            return_value=_launch_return(mock_page),
        ),
        patch("playwright.sync_api.sync_playwright", return_value=_sync_playwright_cm()[0]),
        patch("agentzero.scrape.browser_board.close_browser_session"),
        patch(
            "agentzero.scrape.browser_board.validate_browser_page_url",
            return_value=True,
        ),
        patch("agentzero.scrape.browser_board.wait_for_html", return_value=html),
        patch("agentzero.scrape.browser_board.maybe_wait_for_human"),
        patch("agentzero.scrape.browser_board.click_consent_buttons") as consent,
    ):
        records = list(source.fetch())
    consent.assert_called()
    assert records


def test_browser_job_board_title_filter_drops_off_topic(tmp_path):
    html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Nurse Practitioner"],
        locations=["Remote"],
        results_wanted=10,
        scrape_session_preflight=False,
        scrape_browser_headless=True,
    )
    source = BrowserJobBoardSource(settings, site="indeed")
    mock_page = MagicMock()
    mock_page.url = "https://www.indeed.com/jobs"
    mock_page.content.return_value = html
    with (
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            return_value=_launch_return(mock_page),
        ),
        patch("playwright.sync_api.sync_playwright", return_value=_sync_playwright_cm()[0]),
        patch("agentzero.scrape.browser_board.close_browser_session"),
        patch(
            "agentzero.scrape.browser_board.validate_browser_page_url",
            return_value=True,
        ),
        patch("agentzero.scrape.browser_board.wait_for_html", return_value=html),
        patch("agentzero.scrape.browser_board.maybe_wait_for_human"),
        patch("agentzero.scrape.browser_indeed._dismiss_indeed_consent"),
    ):
        assert source.fetch() == []


def test_browser_job_board_fetch_exception_returns_empty(tmp_path):
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Engineer"],
        locations=["Remote"],
        scrape_session_preflight=False,
    )
    source = BrowserJobBoardSource(settings, site="indeed")
    with (
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            side_effect=RuntimeError("boom"),
        ),
        patch("playwright.sync_api.sync_playwright", return_value=_sync_playwright_cm()[0]),
        patch("agentzero.scrape.browser_board.close_browser_session"),
    ):
        assert source.fetch() == []


def test_browser_job_board_preflight_login_skips(tmp_path):
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        scrape_session_preflight=True,
        search_terms=["Engineer"],
        locations=["Remote"],
    )
    source = BrowserJobBoardSource(settings, site="indeed")
    mock_page = MagicMock()
    mock_page.url = "https://www.indeed.com/account/login"
    mock_page.content.return_value = "<html>sign in</html>"
    with (
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            return_value=_launch_return(mock_page),
        ),
        patch("playwright.sync_api.sync_playwright", return_value=_sync_playwright_cm()[0]),
        patch("agentzero.scrape.browser_board.close_browser_session"),
        patch(
            "agentzero.scrape.browser_board.validate_browser_page_url",
            return_value=True,
        ),
    ):
        assert source.fetch() == []


def test_browser_job_board_pause_reloads_when_still_blocked(tmp_path):
    html_blocked = "<html>verify you are human</html>"
    html_ok = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Staff Security Engineer"],
        locations=["Remote"],
        results_wanted=5,
        scrape_session_preflight=False,
        scrape_browser_headless=False,
        scrape_browser_pause_for_captcha=True,
    )
    source = BrowserJobBoardSource(settings, site="indeed", input_fn=lambda _: "")
    mock_page = MagicMock()
    mock_page.url = "https://www.indeed.com/jobs"
    mock_page.content.side_effect = [html_blocked, html_blocked, html_ok, html_ok]
    with (
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            return_value=_launch_return(mock_page),
        ),
        patch("playwright.sync_api.sync_playwright", return_value=_sync_playwright_cm()[0]),
        patch("agentzero.scrape.browser_board.close_browser_session"),
        patch(
            "agentzero.scrape.browser_board.validate_browser_page_url",
            return_value=True,
        ),
        patch(
            "agentzero.scrape.browser_board.wait_for_html",
            side_effect=[html_blocked, html_ok, html_ok],
        ),
        patch("agentzero.scrape.browser_board.maybe_wait_for_human"),
        patch("agentzero.scrape.browser_indeed._dismiss_indeed_consent"),
    ):
        records = list(source.fetch())
    assert len(records) == 2


def test_browser_job_board_empty_parse_retries_wait(tmp_path):
    html_empty = "<html><body>no jobs</body></html>"
    html_ok = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Staff Security Engineer"],
        locations=["Remote"],
        results_wanted=5,
        scrape_session_preflight=False,
        scrape_browser_headless=True,
    )
    source = BrowserJobBoardSource(settings, site="indeed")
    mock_page = MagicMock()
    mock_page.url = "https://www.indeed.com/jobs"
    mock_page.content.return_value = html_ok
    with (
        patch(
            "agentzero.scrape.browser_board.launch_browser_page",
            return_value=_launch_return(mock_page),
        ),
        patch("playwright.sync_api.sync_playwright", return_value=_sync_playwright_cm()[0]),
        patch("agentzero.scrape.browser_board.close_browser_session"),
        patch(
            "agentzero.scrape.browser_board.validate_browser_page_url",
            return_value=True,
        ),
        patch(
            "agentzero.scrape.browser_board.wait_for_html",
            side_effect=[html_empty, html_ok],
        ),
        patch("agentzero.scrape.browser_board.maybe_wait_for_human"),
        patch("agentzero.scrape.browser_indeed._dismiss_indeed_consent"),
    ):
        records = list(source.fetch())
    assert len(records) == 2


def test_default_input_eof_returns_empty(monkeypatch):
    def boom(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)
    assert _default_input("> ") == ""
