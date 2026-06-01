"""Tests for outbound URL safety validation."""

import socket
from unittest.mock import patch

import pytest

from agentzero.net.url_safety import (
    UnsafeURLError,
    is_safe_public_url,
    url_host_matches,
    validate_fetch_url,
)


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


def test_accepts_public_ip_literal():
    validate_fetch_url("http://8.8.8.8/dns")


def test_rejects_multicast_ip_literal():
    with pytest.raises(UnsafeURLError):
        validate_fetch_url("http://224.0.0.1/")


def test_rejects_dot_localhost_and_dot_local():
    assert not is_safe_public_url("http://app.localhost/admin")
    assert not is_safe_public_url("http://printer.local/status")


def test_rejects_metadata_host_by_name():
    with pytest.raises(UnsafeURLError, match="metadata"):
        validate_fetch_url("http://metadata.google.internal/")


def test_rejects_missing_hostname():
    with pytest.raises(UnsafeURLError, match="missing hostname"):
        validate_fetch_url("http:///path")


def test_url_host_matches_exact_subdomain_and_rejects_lookalikes():
    assert url_host_matches("https://www.indeed.com/jobs", "indeed.com")
    assert url_host_matches("https://indeed.com/", "indeed.com")
    assert not url_host_matches("https://notindeed.com/", "indeed.com")
    assert not url_host_matches("https://indeed.com.evil.example/", "indeed.com")


@patch("agentzero.net.url_safety.socket.getaddrinfo")
def test_rejects_host_resolving_to_private_ip(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
    ]
    with pytest.raises(UnsafeURLError, match="non-public"):
        validate_fetch_url("http://evil.example.com/")


@patch("agentzero.net.url_safety.socket.getaddrinfo")
def test_rejects_unresolvable_host(mock_getaddrinfo):
    mock_getaddrinfo.side_effect = socket.gaierror("name resolution failed")
    with pytest.raises(UnsafeURLError, match="Cannot resolve"):
        validate_fetch_url("http://does-not-resolve.example/")


@patch("agentzero.net.url_safety.socket.getaddrinfo")
def test_rejects_host_with_no_usable_addresses(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("not-an-ip", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", None),
    ]
    with pytest.raises(UnsafeURLError, match="No usable addresses"):
        validate_fetch_url("http://bad.example/")


@patch("agentzero.net.url_safety.socket.getaddrinfo")
def test_deduplicates_resolved_addresses(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0)),
    ]
    assert validate_fetch_url("http://one.one.one.one/") == "http://one.one.one.one/"
