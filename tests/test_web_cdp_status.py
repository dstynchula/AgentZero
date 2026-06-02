from unittest.mock import patch

from agentzero.config import Settings
from agentzero.web.cdp_status import (
    build_host_instructions,
    cdp_status_payload,
    enabled_cdp_browser_sites,
    retry_cdp_connection,
)
from agentzero.web.operator_config import OperatorScrapeConfig


def test_launch_commands_when_cdp_needed():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed"],
        scrape_cdp_url="http://127.0.0.1:9222",
        scrape_cdp_sites=["indeed"],
    )
    payload = cdp_status_payload(settings, None)
    assert len(payload["launch_commands"]) == 3
    commands = " ".join(c["command"] for c in payload["launch_commands"])
    assert "launch_chrome_cdp.ps1" in commands
    assert "launch_chrome_cdp.py" in commands
    assert "launch_chrome_cdp.sh" in commands


def test_host_instructions_only_enabled_sources():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        scrape_sites=["google", "zip_recruiter"],
        scrape_cdp_url="http://127.0.0.1:9222",
        scrape_cdp_sites=["indeed", "glassdoor"],
    )
    op = OperatorScrapeConfig(scrape_browser_sites=["indeed"], scrape_sites=["google"])
    text = build_host_instructions(settings, op)
    assert "Indeed" in text
    assert "Google Jobs" in text
    assert "LinkedIn" not in text
    assert "ZipRecruiter" not in text
    assert "Glassdoor" not in text
    assert "launch_chrome_cdp.ps1" not in text


def test_cdp_not_needed_when_only_linkedin():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["linkedin"],
        scrape_cdp_url="http://127.0.0.1:9222",
    )
    payload = cdp_status_payload(settings, None)
    assert payload["needs_cdp"] is False


def test_enabled_cdp_browser_sites():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "glassdoor"],
        scrape_cdp_url="http://127.0.0.1:9222",
        scrape_cdp_sites=["indeed"],
    )
    op = OperatorScrapeConfig(scrape_browser_sites=["indeed", "glassdoor"])
    assert enabled_cdp_browser_sites(settings, op) == ["indeed"]


def test_retry_cdp_when_already_reachable():
    settings = Settings(_env_file=None, scrape_cdp_url="http://127.0.0.1:9222")
    with patch("agentzero.web.cdp_status.cdp_endpoint_reachable", return_value=True):
        ok, msg = retry_cdp_connection(settings, None)
    assert ok is True
    assert "Connected" in msg


def test_retry_cdp_without_url():
    settings = Settings(_env_file=None, scrape_cdp_url=None)
    ok, msg = retry_cdp_connection(settings, None)
    assert ok is False
    assert "AGENTZERO_SCRAPE_CDP_URL" in msg
