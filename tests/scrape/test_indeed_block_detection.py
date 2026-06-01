"""Indeed block-page detection after CAPTCHA."""

from __future__ import annotations

from agentzero.scrape.browser_indeed import (
    page_has_job_results,
    page_needs_human,
    page_needs_login,
)


def test_page_needs_human_ray_id_stale_page():
    html = "<html><body><p>Your Ray ID for this request is abc123def</p></body></html>"
    assert page_needs_human(html, "https://www.indeed.com/jobs?q=engineer")
    assert not page_has_job_results(html)


def test_page_needs_human_false_when_mosaic_present():
    html = 'x' * 100 + 'mosaic-provider-jobcards' + 'y' * 100
    assert page_has_job_results(html)
    assert not page_needs_human(html, "https://www.indeed.com/jobs")


def test_page_needs_human_sorry_short_page():
    html = "<html><body>sorry indeed blocked</body></html>"
    assert page_needs_human(html, "https://www.indeed.com/jobs")


def test_page_needs_human_skips_login_wall():
    html = "<html>ready to take the next step create an account or sign in</html>"
    assert not page_needs_human(html, "https://www.indeed.com/account/login")
    assert page_needs_login(html, "https://www.indeed.com/account/login")


def test_page_needs_human_captcha_url_tokens():
    assert page_needs_human("", "https://www.indeed.com/captcha")
    assert page_needs_human("", "https://www.indeed.com/challenge/abc")
