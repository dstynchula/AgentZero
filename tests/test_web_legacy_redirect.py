from urllib.parse import urlparse

from fastapi import Request

from agentzero.web.legacy_redirect import (
    legacy_api_scraper_redirect_url,
    legacy_scraper_redirect_url,
    safe_legacy_scraper_path,
)


def _request(path: str = "/", query: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query.encode() if query else b"",
        "headers": [],
    }
    return Request(scope)


def test_safe_legacy_scraper_path_rejects_open_redirect():
    assert safe_legacy_scraper_path("//evil.example") == ""
    assert safe_legacy_scraper_path("https://evil.example/x") == ""
    assert safe_legacy_scraper_path("../admin") == ""
    assert safe_legacy_scraper_path("unknown/route") == ""


def test_safe_legacy_scraper_path_allows_known_routes():
    assert safe_legacy_scraper_path("sources") == "sources"
    assert safe_legacy_scraper_path("/cdp/connect") == "cdp/connect"


def test_legacy_scraper_redirect_filters_query():
    req = _request(query="saved=1&next=https://evil.example")
    url = legacy_scraper_redirect_url(req, "sources")
    assert url == "/scraper/sources?saved=1"
    parsed = urlparse(url)
    assert parsed.scheme == ""
    assert parsed.netloc == ""


def test_legacy_scraper_redirect_unknown_path_falls_back_to_root():
    req = _request(query="saved=1")
    assert legacy_scraper_redirect_url(req, "//evil.example") == "/scraper?saved=1"


def test_legacy_api_scraper_redirect_is_relative():
    req = _request(query="cdp_ok=1&evil=https://bad")
    assert legacy_api_scraper_redirect_url(req) == "/api/scraper?cdp_ok=1"
