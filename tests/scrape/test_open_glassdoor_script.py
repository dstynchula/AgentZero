"""Smoke tests for open_glassdoor_browser URL builder."""

from __future__ import annotations

from scripts.open_glassdoor_browser import build_search_url


def test_build_search_url_remote():
    url = build_search_url(query="Staff Security Engineer", location="Remote", remote=True)
    assert "sc.keyword=Staff" in url or "Staff+Security" in url
    assert "glassdoor.com" in url
    assert "remoteWorkType=1" in url


def test_build_search_url_office():
    url = build_search_url(query="Engineer", location="Los Angeles, CA", remote=False)
    assert "Los+Angeles" in url or "Los%20Angeles" in url
    assert "remoteWorkType" not in url
