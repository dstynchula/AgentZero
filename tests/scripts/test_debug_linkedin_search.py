"""Tests for scripts/debug_linkedin_search.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentzero.config import Settings
from scripts.debug_linkedin_search import main


def test_debug_cli_prints_json_summary_mocked():
    mock_result = MagicMock()
    mock_result.url = "https://www.linkedin.com/jobs/search"
    mock_result.login_required = False
    mock_result.error = None
    mock_result.session_state = "ready"
    mock_result.has_job_markers = True
    mock_result.parsed_raw = 5
    mock_result.after_title_filter = 3
    mock_result.records = [{"title": "Staff Security Engineer", "company": "Acme"}]
    mock_result.html_snapshot = None

    settings = Settings(
        _env_file=None,
        search_terms=["Engineer"],
        locations=["Remote"],
        scrape_cdp_sites=[],
    )

    with (
        patch("agentzero.config.get_settings", return_value=settings),
        patch("agentzero.scrape.linkedin_jobs.LinkedInJobsService") as mock_svc,
    ):
        mock_svc.return_value.search.return_value = mock_result
        code = main(["--live", "--terms", "Engineer", "--locations", "Remote"])

    assert code == 0


def test_debug_cli_live_flag_requires_explicit(capsys):
    code = main(["--terms", "Engineer"])
    assert code == 2
    err = capsys.readouterr().err
    assert "--live" in err


def test_debug_cli_dry_run_prints_settings(capsys):
    with patch("agentzero.config.get_settings") as mock_settings:
        mock_settings.return_value.model_copy.return_value = MagicMock(
            search_terms=["Engineer"],
            locations=["Remote"],
            remote_only=False,
            scrape_browser_headless=True,
            scrape_cdp_sites=[],
            scrape_cdp_url="",
            scrape_browser_profile_dir=Path("data/browser_profiles"),
        )
        code = main(["--dry-run"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
