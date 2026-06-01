"""Tests for browser session health classification."""

from __future__ import annotations

from pathlib import Path

from agentzero.scrape.browser_session import SessionState, classify_session

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_glassdoor_results_ready():
    html = _read("glassdoor_results.html")
    assert classify_session("glassdoor", html, "https://www.glassdoor.com/Job/jobs.htm") == SessionState.READY


def test_glassdoor_login_required():
    html = _read("glassdoor_login.html")
    assert (
        classify_session("glassdoor", html, "https://www.glassdoor.com/profile/login_input.htm")
        == SessionState.LOGIN_REQUIRED
    )


def test_glassdoor_captcha_blocked():
    html = _read("glassdoor_captcha.html")
    assert classify_session("glassdoor", html, "https://www.glassdoor.com/Job/jobs.htm") == SessionState.BLOCKED


def test_linkedin_results_ready():
    html = '<html><div class="base-search-card">x</div></html>'
    assert classify_session("linkedin", html, "https://www.linkedin.com/jobs/search/") == SessionState.READY


def test_linkedin_login_required():
    assert (
        classify_session("linkedin", "<html>Sign in</html>", "https://www.linkedin.com/login")
        == SessionState.LOGIN_REQUIRED
    )

def test_indeed_results_ready():
    html = _read("indeed_search.html")
    assert classify_session("indeed", html, "https://www.indeed.com/jobs") == SessionState.READY

