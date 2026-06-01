"""Tests for redirect-aware HTTP client."""

from unittest.mock import MagicMock, patch

from agentzero.net.http_client import safe_get_text


def _stream_response(
    status_code: int,
    *,
    text: str = "",
    headers: dict | None = None,
    url: str = "",
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.url = url
    resp.encoding = "utf-8"
    resp.iter_bytes.return_value = [text.encode("utf-8")] if text else []
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_safe_get_text_rejects_redirect_to_localhost():
    public = _stream_response(
        302,
        headers={"location": "http://127.0.0.1/secret"},
        url="https://example.com/start",
    )

    mock_client = MagicMock()
    mock_client.stream.return_value = public
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        assert safe_get_text("https://example.com/start", user_agent="test") is None


def test_safe_get_text_follows_safe_redirect():
    redirect = _stream_response(
        302,
        headers={"location": "/final"},
        url="https://example.com/start",
    )
    ok = _stream_response(200, text="hello", url="https://example.com/final")

    mock_client = MagicMock()
    mock_client.stream.side_effect = [redirect, ok]
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        assert safe_get_text("https://example.com/start", user_agent="test") == "hello"


def test_safe_get_text_truncates_large_body():
    body = "x" * 5000
    ok = _stream_response(200, text=body, url="https://example.com/page")

    mock_client = MagicMock()
    mock_client.stream.return_value = ok
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        result = safe_get_text(
            "https://example.com/page",
            user_agent="test",
            max_bytes=1000,
        )
    assert result is not None
    assert len(result.encode("utf-8")) <= 1000
