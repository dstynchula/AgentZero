"""Tests for login vs CAPTCHA page detection on browser job boards."""

from __future__ import annotations

from pathlib import Path

from agentzero.scrape.browser_glassdoor import (
    page_has_job_results,
    page_needs_human,
    page_needs_login,
    page_session_ready,
)
from agentzero.scrape.browser_indeed import (
    page_needs_human as indeed_needs_human,
)
from agentzero.scrape.browser_indeed import (
    page_needs_login as indeed_needs_login,
)
from agentzero.scrape.browser_indeed import (
    page_session_ready as indeed_session_ready,
)
from agentzero.scrape.browser_linkedin import (
    page_needs_human as linkedin_needs_human,
)
from agentzero.scrape.browser_linkedin import (
    page_needs_login as linkedin_needs_login,
)
from agentzero.scrape.browser_linkedin import (
    page_session_ready as linkedin_session_ready,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestGlassdoorPages:
    def test_login_page_detected(self):
        html = _read("glassdoor_login.html")
        url = "https://www.glassdoor.com/profile/login_input.htm"
        assert page_needs_login(html, url) is True
        assert page_needs_human(html, url) is False
        assert page_session_ready(html, url) is False

    def test_captcha_page_not_login(self):
        html = _read("glassdoor_captcha.html")
        url = "https://www.glassdoor.com/Job/jobs.htm"
        assert page_needs_login(html, url) is False
        assert page_needs_human(html, url) is True
        assert page_session_ready(html, url) is False

    def test_results_page_ready(self):
        html = _read("glassdoor_results.html")
        url = "https://www.glassdoor.com/Job/jobs.htm"
        assert page_has_job_results(html) is True
        assert page_needs_login(html, url) is False
        assert page_needs_human(html, url) is False
        assert page_session_ready(html, url) is True


class TestLinkedInPages:
    def test_login_url(self):
        html = "<html><body>Sign in</body></html>"
        assert linkedin_needs_login(html, "https://www.linkedin.com/login") is True
        assert linkedin_needs_human(html, "https://www.linkedin.com/login") is False

    def test_authwall_is_login_not_captcha(self):
        html = "<html><body>Join LinkedIn</body></html>"
        url = "https://www.linkedin.com/authwall"
        assert linkedin_needs_login(html, url) is True
        assert linkedin_needs_human(html, url) is False

    def test_results_ready(self):
        html = '<html><div class="base-search-card">job</div></html>'
        assert linkedin_session_ready(html, "https://www.linkedin.com/jobs/search/") is True
        assert linkedin_needs_login(html, "https://www.linkedin.com/jobs/search/") is False

    def test_captcha_distinct_from_login(self):
        html = "<html><body>captcha challenge verify</body></html>"
        url = "https://www.linkedin.com/jobs/search/"
        assert linkedin_needs_login(html, url) is False
        assert linkedin_needs_human(html, url) is True


class TestIndeedPages:
    def test_login_page_detected(self):
        html = _read("indeed_login.html")
        url = "https://secure.indeed.com/account/login?hl=en&continue=https%3A%2F%2Fwww.indeed.com"
        assert indeed_needs_login(html, url) is True
        assert indeed_needs_human(html, url) is False
        assert indeed_session_ready(html, url) is False

    def test_logged_in_home_not_login(self):
        html = "<html><body><nav>Find jobs</nav></body></html>"
        url = "https://www.indeed.com/"
        assert indeed_needs_login(html, url) is False
        assert indeed_session_ready(html, url) is True


class TestBrowserAuthNeedsLogin:
    def test_indeed_login_url_waits(self):
        from agentzero.scrape.browser_auth import INDEED_LOGIN_URL, _still_on_login_wall

        html = _read("indeed_login.html")
        assert "account/login" in INDEED_LOGIN_URL
        assert _still_on_login_wall(
            "indeed",
            html,
            "https://secure.indeed.com/account/login?hl=en&continue=https%3A%2F%2Fwww.indeed.com",
        )

    def test_indeed_home_not_login_wall(self):
        from agentzero.scrape.browser_auth import _still_on_login_wall

        html = "<html><body><nav>Find jobs</nav></body></html>"
        assert not _still_on_login_wall("indeed", html, "https://www.indeed.com/")

    def test_glassdoor_uses_login_detector(self):
        from agentzero.scrape.browser_auth import _still_on_login_wall

        html = _read("glassdoor_login.html")
        assert _still_on_login_wall("glassdoor", html, "https://www.glassdoor.com/profile/login_input.htm")

    def test_glassdoor_captcha_not_login_wall(self):
        from agentzero.scrape.browser_auth import _still_on_login_wall

        html = _read("glassdoor_captcha.html")
        assert not _still_on_login_wall("glassdoor", html, "https://www.glassdoor.com/Job/jobs.htm")
