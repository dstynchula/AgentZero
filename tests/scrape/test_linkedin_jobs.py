"""Tests for LinkedInJobsService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agentzero.config import Settings
from agentzero.scrape.linkedin_jobs import LinkedInJobsService, LinkedInSearchResult

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_search_result_debug_fields_default_none():
    result = LinkedInSearchResult()
    assert result.parsed_raw is None
    assert result.after_title_filter is None
    assert result.session_state is None
    assert result.has_job_markers is None
    assert result.html_snapshot is None


def test_search_jobs_parses_fixture_html(tmp_path):
    html = (FIXTURES / "linkedin_search_spa.html").read_text(encoding="utf-8")
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Staff Security Engineer"],
        locations=["remote - usa"],
        scrape_session_preflight=False,
        scrape_browser_headless=True,
        scrape_browser_pause_for_captcha=False,
    )
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/jobs/search"
    mock_page.content.return_value = html
    service = LinkedInJobsService(settings)
    with (
        patch(
            "agentzero.scrape.linkedin_jobs.launch_browser_page",
            return_value=(MagicMock(), MagicMock(), mock_page, None),
        ),
        patch("agentzero.scrape.linkedin_jobs.close_browser_session"),
        patch(
            "agentzero.scrape.linkedin_jobs.validate_browser_page_url",
            return_value=True,
        ),
        patch("agentzero.scrape.linkedin_jobs.wait_for_html", return_value=html),
        patch("agentzero.scrape.linkedin_jobs.maybe_wait_for_human"),
        patch("agentzero.scrape.linkedin_jobs.click_consent_buttons"),
        patch("agentzero.scrape.linkedin_jobs._prepare_search_page"),
    ):
        result = service.search()
    assert not result.login_required
    assert len(result.records) >= 1
    assert "linkedin.com" in result.url
    assert (result.after_title_filter or 0) >= 1


def test_parse_with_retry_reports_dropped_titles():
    settings = Settings(
        _env_file=None,
        search_terms=["Staff Security Engineer"],
        locations=["remote - usa"],
    )
    service = LinkedInJobsService(settings)
    mock_page = MagicMock()
    raw = [
        {
            "title": "Staff Security Engineer",
            "company": "Acme",
            "url": "https://www.linkedin.com/jobs/view/1111111111",
            "source": "linkedin",
        },
        {
            "title": "VP of Marketing",
            "company": "Other",
            "url": "https://www.linkedin.com/jobs/view/2222222222",
            "source": "linkedin",
        },
    ]
    with patch(
        "agentzero.scrape.linkedin_jobs.parse_linkedin_search_html",
        return_value=raw,
    ):
        records, stats = service._parse_with_retry(  # noqa: SLF001
            mock_page,
            url="https://www.linkedin.com/jobs/search/",
            term="Staff Security Engineer",
            parsed_remote=False,
        )
    assert stats.parsed_raw == 2
    assert stats.after_title_filter == 1
    assert len(records) == 1


def test_search_waits_for_network_idle_or_scroll_before_parse(tmp_path):
    html = (FIXTURES / "linkedin_search_spa.html").read_text(encoding="utf-8")
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Staff Security Engineer"],
        locations=["remote - usa"],
        scrape_session_preflight=False,
    )
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/jobs/search"
    mock_page.content.return_value = html
    service = LinkedInJobsService(settings)
    with (
        patch(
            "agentzero.scrape.linkedin_jobs.launch_browser_page",
            return_value=(MagicMock(), MagicMock(), mock_page, None),
        ),
        patch("agentzero.scrape.linkedin_jobs.close_browser_session"),
        patch(
            "agentzero.scrape.linkedin_jobs.validate_browser_page_url",
            return_value=True,
        ),
        patch("agentzero.scrape.linkedin_jobs.wait_for_html", return_value=html),
        patch("agentzero.scrape.linkedin_jobs.maybe_wait_for_human"),
        patch("agentzero.scrape.linkedin_jobs.click_consent_buttons"),
        patch("agentzero.scrape.linkedin_jobs._prepare_search_page") as mock_prep,
    ):
        service.search()
    assert mock_prep.call_count >= 1


def test_search_jobs_login_required_returns_empty(tmp_path):
    login_html = "<html>sign in join linkedin</html>"
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        scrape_session_preflight=True,
        search_terms=["Engineer"],
        locations=["Remote"],
    )
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/login"
    mock_page.content.return_value = login_html
    service = LinkedInJobsService(settings)
    with (
        patch(
            "agentzero.scrape.linkedin_jobs.launch_browser_page",
            return_value=(MagicMock(), MagicMock(), mock_page, None),
        ),
        patch("agentzero.scrape.linkedin_jobs.close_browser_session"),
        patch(
            "agentzero.scrape.linkedin_jobs.validate_browser_page_url",
            return_value=True,
        ),
        patch("agentzero.scrape.linkedin_jobs.wait_for_html", return_value=login_html),
        patch("agentzero.scrape.linkedin_jobs.maybe_wait_for_human"),
        patch("agentzero.scrape.linkedin_jobs.click_consent_buttons"),
        patch("agentzero.scrape.linkedin_jobs._prepare_search_page"),
        patch(
            "agentzero.scrape.linkedin_jobs._safe_page_content",
            return_value=login_html,
        ),
    ):
        result = service.search()
    assert result.login_required
    assert result.records == []


def test_search_retries_transient_empty(tmp_path):
    html_empty = "<html><body>no jobs</body></html>"
    html_ok = (FIXTURES / "linkedin_search_spa.html").read_text(encoding="utf-8")
    settings = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "prof",
        search_terms=["Staff Security Engineer"],
        locations=["remote - usa"],
        scrape_session_preflight=False,
        scrape_browser_headless=True,
    )
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/jobs/search"
    mock_page.content.side_effect = [html_empty, html_ok]
    service = LinkedInJobsService(settings)
    with (
        patch(
            "agentzero.scrape.linkedin_jobs.launch_browser_page",
            return_value=(MagicMock(), MagicMock(), mock_page, None),
        ),
        patch("agentzero.scrape.linkedin_jobs.close_browser_session"),
        patch(
            "agentzero.scrape.linkedin_jobs.validate_browser_page_url",
            return_value=True,
        ),
        patch(
            "agentzero.scrape.linkedin_jobs.wait_for_html",
            side_effect=[html_empty, html_ok, html_ok],
        ),
        patch("agentzero.scrape.linkedin_jobs.maybe_wait_for_human"),
        patch("agentzero.scrape.linkedin_jobs.click_consent_buttons"),
        patch("agentzero.scrape.linkedin_jobs._prepare_search_page"),
    ):
        result = service.search()
    assert len(result.records) >= 1
