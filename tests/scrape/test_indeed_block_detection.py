"""Indeed block-page detection after CAPTCHA."""

from __future__ import annotations

from agentzero.scrape.browser_indeed import page_has_job_results, page_needs_human


def test_page_needs_human_ray_id_stale_page():
    html = "<html><body><p>Your Ray ID for this request is abc123def</p></body></html>"
    assert page_needs_human(html, "https://www.indeed.com/jobs?q=engineer")
    assert not page_has_job_results(html)


def test_page_needs_human_false_when_mosaic_present():
    html = 'x' * 100 + 'mosaic-provider-jobcards' + 'y' * 100
    assert page_has_job_results(html)
    assert not page_needs_human(html, "https://www.indeed.com/jobs")
