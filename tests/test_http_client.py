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


def test_safe_get_text_returns_none_when_httpx_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "httpx":
            raise ImportError("no httpx")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert safe_get_text("https://example.com/", user_agent="test") is None


def test_safe_get_text_redirect_without_location_returns_none():
    redirect = _stream_response(302, headers={}, url="https://example.com/start")
    mock_client = MagicMock()
    mock_client.stream.return_value = redirect
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        assert safe_get_text("https://example.com/start", user_agent="test") is None


def test_safe_get_text_http_error_returns_none():
    err = _stream_response(404, url="https://example.com/missing")
    mock_client = MagicMock()
    mock_client.stream.return_value = err
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        assert safe_get_text("https://example.com/missing", user_agent="test") is None


def test_safe_get_text_applies_max_chars():
    ok = _stream_response(200, text="abcdef", url="https://example.com/page")
    mock_client = MagicMock()
    mock_client.stream.return_value = ok
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        assert (
            safe_get_text(
                "https://example.com/page",
                user_agent="test",
                max_bytes=None,
                max_chars=3,
            )
            == "abc"
        )


def test_safe_get_text_skips_empty_chunks():
    ok = _stream_response(200, url="https://example.com/page")
    ok.iter_bytes.return_value = [b"", b"hi", b""]

    mock_client = MagicMock()
    mock_client.stream.return_value = ok
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        assert safe_get_text("https://example.com/page", user_agent="test") == "hi"


def test_safe_get_text_truncates_across_multiple_chunks():
    ok = _stream_response(200, url="https://example.com/page")
    ok.iter_bytes.return_value = [b"a" * 900, b"b" * 900]

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
    assert len(result.encode("utf-8")) == 1000


def test_safe_get_text_too_many_redirects_returns_none():
    redirect = _stream_response(
        302,
        headers={"location": "/next"},
        url="https://example.com/start",
    )
    mock_client = MagicMock()
    mock_client.stream.side_effect = [redirect] * 7
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        assert safe_get_text("https://example.com/start", user_agent="test") is None


def test_safe_get_text_handles_stream_exception():
    mock_client = MagicMock()
    mock_client.stream.side_effect = RuntimeError("network down")
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        assert safe_get_text("https://example.com/page", user_agent="test") is None
