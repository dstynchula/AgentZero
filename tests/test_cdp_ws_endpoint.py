"""Tests for Docker CDP WebSocket endpoint rewriting."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from agentzero.scrape.browser_common import (
    resolve_cdp_ws_endpoint,
    rewrite_cdp_ws_url_for_client,
)


def test_rewrite_cdp_ws_url_for_client_loopback_to_docker_host():
    ws = "ws://127.0.0.1:9223/devtools/browser/abc"
    out = rewrite_cdp_ws_url_for_client(
        ws,
        cdp_http_url="http://host.docker.internal:9222",
        allow_docker_host=True,
    )
    assert out == "ws://host.docker.internal:9222/devtools/browser/abc"


def test_rewrite_cdp_ws_url_unchanged_for_local_cdp():
    ws = "ws://127.0.0.1:9222/devtools/browser/abc"
    assert (
        rewrite_cdp_ws_url_for_client(
            ws,
            cdp_http_url="http://127.0.0.1:9222",
            allow_docker_host=True,
        )
        is None
    )


def test_rewrite_cdp_ws_url_rejects_disallowed_remote_host():
    ws = "ws://evil.example:9222/devtools/browser/abc"
    assert (
        rewrite_cdp_ws_url_for_client(
            ws,
            cdp_http_url="http://host.docker.internal:9222",
            allow_docker_host=True,
        )
        is None
    )


def test_resolve_cdp_ws_endpoint_fetches_version_json():
    payload = {
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/test-id",
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ws = resolve_cdp_ws_endpoint(
            "http://host.docker.internal:9222",
            allow_docker_host=True,
        )

    assert ws == "ws://host.docker.internal:9222/devtools/browser/test-id"


def test_resolve_cdp_ws_endpoint_returns_none_for_localhost_cdp():
    assert resolve_cdp_ws_endpoint("http://127.0.0.1:9222", allow_docker_host=True) is None


def test_resolve_cdp_ws_endpoint_returns_none_on_fetch_error():
    with patch("urllib.request.urlopen", side_effect=URLError("down")):
        assert (
            resolve_cdp_ws_endpoint(
                "http://host.docker.internal:9222",
                allow_docker_host=True,
            )
            is None
        )
