"""Tests for outbound URL safety validation."""

import pytest

from agentzero.net.url_safety import UnsafeURLError, is_safe_public_url, validate_fetch_url


def test_accepts_public_https():
    assert is_safe_public_url("https://example.com/jobs/1")
    validate_fetch_url("https://www.linkedin.com/jobs/view/123")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "ftp://example.com/x",
        "not-a-url",
    ],
)
def test_rejects_unsafe_urls(url: str):
    assert not is_safe_public_url(url)
    with pytest.raises(UnsafeURLError):
        validate_fetch_url(url)


def test_rejects_private_ip_literal():
    with pytest.raises(UnsafeURLError):
        validate_fetch_url("http://10.0.0.1/internal")
