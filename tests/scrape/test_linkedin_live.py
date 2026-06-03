"""Live LinkedIn scrape smoke (skipped unless AGENTZERO_LINKEDIN_LIVE=1)."""

from __future__ import annotations

import os

import pytest

from agentzero.config import get_settings
from agentzero.scrape.linkedin_jobs import LinkedInJobsService

pytestmark = pytest.mark.external


@pytest.mark.skipif(
    os.environ.get("AGENTZERO_LINKEDIN_LIVE") != "1",
    reason="Set AGENTZERO_LINKEDIN_LIVE=1 to run live LinkedIn browser test",
)
def test_linkedin_live_search_returns_minimum_rows():
    settings = get_settings().model_copy(
        update={
            "search_terms": ["Staff Security Engineer"],
            "locations": ["Remote - USA"],
            "remote_only": True,
            "scrape_browser_sites": ["linkedin"],
            "scrape_session_preflight": True,
            "scrape_browser_headless": False,
            "scrape_browser_pause_for_captcha": True,
            "results_wanted": 25,
        }
    )
    result = LinkedInJobsService(settings).search()
    assert not result.login_required, f"login required (state={result.session_state})"
    assert result.error is None, result.error
    assert (result.after_title_filter or 0) >= 3, (
        f"expected >=3 rows, got parsed_raw={result.parsed_raw} "
        f"after_filter={result.after_title_filter} markers={result.has_job_markers}"
    )
