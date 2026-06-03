import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> pathlib.Path:
    return REPO_ROOT


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.external unless AGENTZERO_LINKEDIN_LIVE=1."""
    import os

    if os.environ.get("AGENTZERO_LINKEDIN_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="external tests require AGENTZERO_LINKEDIN_LIVE=1")
    for item in items:
        if "external" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch):
    """Unit tests must not hit DuckDuckGo, Glassdoor, or job-board HTTP."""
    monkeypatch.setenv("AGENTZERO_ENRICH_WEB_SEARCH", "false")
    monkeypatch.setattr(
        "agentzero.enrich.web_search.search_web",
        lambda *args, **kwargs: [],
    )


@pytest.fixture
def pipeline_test_settings():
    """Settings for Pipeline tests — no live web enrichment."""
    from agentzero.config import Settings

    def _factory(**kwargs):
        base = dict(_env_file=None, remote_only=False, enrich_web_search=False)
        base.update(kwargs)
        return Settings(**base)

    return _factory
