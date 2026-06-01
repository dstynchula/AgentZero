"""Tests for CDP URL validation."""

import pytest

from agentzero.net.cdp_safety import UnsafeCDPURLError, validate_cdp_url


def test_validate_cdp_url_accepts_localhost():
    assert validate_cdp_url("http://127.0.0.1:9222") == "http://127.0.0.1:9222"
    assert validate_cdp_url("http://localhost:9222") == "http://localhost:9222"


def test_validate_cdp_url_rejects_remote():
    with pytest.raises(UnsafeCDPURLError, match="localhost"):
        validate_cdp_url("http://192.168.1.10:9222")
