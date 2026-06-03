"""Tests for launch_browser_page modes (mocked Playwright)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from agentzero.config import Settings


def test_build_launch_args_skips_blink_flag_for_system_chrome():
    from agentzero.scrape.browser_common import build_launch_args

    bundled = Settings(_env_file=None, scrape_browser_channel=None)
    system = Settings(_env_file=None, scrape_browser_channel="chrome")

    assert "--disable-blink-features=AutomationControlled" in build_launch_args(bundled, headless=False)
    assert "--disable-blink-features=AutomationControlled" not in build_launch_args(system, headless=False)
    assert "--start-maximized" in build_launch_args(system, headless=False)


def test_launch_browser_page_uses_channel(tmp_path):
    s = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "indeed_browser_profile",
        scrape_browser_channel="chrome",
    )
    mock_pw = MagicMock()
    mock_context = MagicMock()
    mock_context.pages = []
    mock_context.new_page.return_value = MagicMock()
    mock_pw.chromium.launch_persistent_context.return_value = mock_context

    with patch("playwright.sync_api.sync_playwright", return_value=MagicMock(start=MagicMock(return_value=mock_pw))):
        from agentzero.scrape.browser_common import launch_browser_page

        pw, ctx, page = launch_browser_page(s, site="linkedin")

    mock_pw.chromium.launch_persistent_context.assert_called_once()
    call_kwargs = mock_pw.chromium.launch_persistent_context.call_args
    assert call_kwargs.kwargs.get("channel") == "chrome"
    assert "--enable-automation" in call_kwargs.kwargs.get("ignore_default_args", [])
    assert "--disable-blink-features=AutomationControlled" not in call_kwargs.kwargs.get("args", [])
    if sys.platform == "win32":
        assert call_kwargs.kwargs.get("chromium_sandbox") is True
    pw.stop()


def test_launch_browser_page_cdp_only_for_configured_sites(tmp_path):
    s = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "indeed_browser_profile",
        scrape_cdp_url="http://127.0.0.1:9222",
        scrape_cdp_sites=["indeed", "glassdoor"],
        scrape_browser_channel="chrome",
        scrape_cdp_auto_launch=False,
    )
    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_browser.contexts = [mock_context]
    mock_context.new_page.return_value = MagicMock()
    mock_pw.chromium.connect_over_cdp.return_value = mock_browser
    mock_pw.chromium.launch_persistent_context.return_value = MagicMock(pages=[])

    with (
        patch("agentzero.scrape.browser_common.cdp_endpoint_reachable", return_value=True),
        patch("playwright.sync_api.sync_playwright", return_value=MagicMock(start=MagicMock(return_value=mock_pw))),
    ):
        from agentzero.scrape.browser_common import close_browser_session, launch_browser_page

        launch_browser_page(s, site="glassdoor")
        mock_pw.chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9222")
        mock_pw.chromium.launch_persistent_context.assert_not_called()

        mock_pw.reset_mock()
        mock_pw.chromium.connect_over_cdp.return_value = mock_browser
        pw, ctx, page = launch_browser_page(s, site="linkedin")
        mock_pw.chromium.connect_over_cdp.assert_not_called()
        mock_pw.chromium.launch_persistent_context.assert_called_once()
        close_browser_session(pw, ctx, s, site="linkedin")
        ctx.close.assert_called_once()


def test_launch_browser_page_cdp_docker_uses_connect_ws_endpoint(tmp_path):
    s = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "indeed_browser_profile",
        scrape_cdp_url="http://host.docker.internal:9222",
        scrape_cdp_sites=["glassdoor"],
        cdp_allow_docker_host=True,
        scrape_cdp_auto_launch=False,
    )
    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_browser.contexts = [mock_context]
    mock_context.new_page.return_value = MagicMock()
    mock_pw.chromium.connect.return_value = mock_browser
    ws = "ws://host.docker.internal:9222/devtools/browser/abc"

    with (
        patch("agentzero.scrape.browser_common.cdp_endpoint_reachable", return_value=True),
        patch("agentzero.scrape.browser_common.resolve_cdp_ws_endpoint", return_value=ws),
        patch("playwright.sync_api.sync_playwright", return_value=MagicMock(start=MagicMock(return_value=mock_pw))),
    ):
        from agentzero.scrape.browser_common import launch_browser_page

        launch_browser_page(s, site="glassdoor")

    mock_pw.chromium.connect.assert_called_once_with(ws_endpoint=ws)
    mock_pw.chromium.connect_over_cdp.assert_not_called()


def test_ensure_cdp_ready_auto_launches_when_down(tmp_path):
    s = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "indeed_browser_profile",
        scrape_cdp_url="http://127.0.0.1:9222",
        scrape_cdp_sites=["glassdoor"],
        scrape_cdp_auto_launch=True,
    )
    with (
        patch("agentzero.scrape.browser_common.cdp_endpoint_reachable", side_effect=[False, True]),
        patch("agentzero.scrape.browser_common.launch_cdp_chrome") as launch,
    ):
        from agentzero.scrape.browser_common import ensure_cdp_ready

        ensure_cdp_ready(s, site="glassdoor")
        launch.assert_called_once_with(s)


def test_launch_applies_storage_state(tmp_path):
    state_dir = tmp_path / "browser_storage_state"
    state_dir.mkdir()
    state_file = state_dir / "glassdoor.json"
    state_file.write_text(
        '{"cookies": [{"name": "gd", "value": "1", "domain": ".glassdoor.com", "path": "/"}]}',
        encoding="utf-8",
    )
    s = Settings(
        _env_file=None,
        scrape_browser_profile_dir=tmp_path / "indeed_browser_profile",
        scrape_storage_state_dir=state_dir,
    )
    mock_pw = MagicMock()
    mock_context = MagicMock()
    mock_context.pages = []
    mock_context.new_page.return_value = MagicMock()
    mock_pw.chromium.launch_persistent_context.return_value = mock_context

    with patch("playwright.sync_api.sync_playwright", return_value=MagicMock(start=MagicMock(return_value=mock_pw))):
        from agentzero.scrape.browser_common import launch_browser_page

        launch_browser_page(s, site="glassdoor")

    mock_context.add_cookies.assert_called_once()
    cookies = mock_context.add_cookies.call_args[0][0]
    assert cookies[0]["name"] == "gd"
