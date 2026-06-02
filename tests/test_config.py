from pathlib import Path

import pytest

from agentzero.config import Settings, get_settings, reload_settings


def test_defaults_without_env():
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai"
    assert s.llm_model == "gpt-5-nano"
    assert s.search_terms == ["software engineer"]
    assert s.locations == ["Remote"]
    assert s.results_wanted == 50
    assert s.proxies == []
    assert isinstance(s.db_path, Path)


def test_env_overrides_and_csv_lists(monkeypatch):
    monkeypatch.setenv("AGENTZERO_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("AGENTZERO_SEARCH_TERMS", "data engineer, ml engineer ,platform engineer")
    monkeypatch.setenv("AGENTZERO_LOCATIONS", "Remote,New York, NY")
    monkeypatch.setenv("AGENTZERO_PROXIES", "host1:8080, host2:8080")
    monkeypatch.setenv("AGENTZERO_RESULTS_WANTED", "25")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    s = Settings(_env_file=None)
    assert s.llm_provider == "anthropic"
    assert s.search_terms == ["data engineer", "ml engineer", "platform engineer"]
    assert s.locations == ["Remote", "New York", "NY"]
    assert s.proxies == ["host1:8080", "host2:8080"]
    assert s.results_wanted == 25
    assert s.anthropic_api_key == "sk-ant-test"


def test_provider_api_key_aliases(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    s = Settings(_env_file=None)
    assert s.openai_api_key == "sk-openai-test"
    assert s.active_api_key == "sk-openai-test"


def test_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENTZERO_OPENAI_API_KEY", raising=False)
    s = Settings(_env_file=None, llm_provider="openai", openai_api_key=None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        _ = s.active_api_key


def test_sheet_id_accepts_full_url(monkeypatch):
    monkeypatch.setenv(
        "AGENTZERO_SHEET_ID",
        "https://docs.google.com/spreadsheets/d/abc123-XYZ/edit#gid=0",
    )
    s = Settings(_env_file=None)
    assert s.sheet_id == "abc123-XYZ"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_reload_settings_clears_cache(monkeypatch):
    first = get_settings()
    monkeypatch.setenv("AGENTZERO_RESULTS_WANTED", "99")
    second = reload_settings()
    assert second is not first
    assert second.results_wanted == 99


def test_cdp_docker_host_when_enabled(monkeypatch):
    monkeypatch.setenv("AGENTZERO_CDP_ALLOW_DOCKER_HOST", "true")
    monkeypatch.setenv("AGENTZERO_SCRAPE_CDP_URL", "http://host.docker.internal:9222")
    s = Settings(_env_file=None)
    assert s.scrape_cdp_url == "http://host.docker.internal:9222"


def test_cdp_docker_host_rejected_without_flag(monkeypatch):
    monkeypatch.delenv("AGENTZERO_CDP_ALLOW_DOCKER_HOST", raising=False)
    with pytest.raises(ValueError, match="host.docker.internal"):
        Settings(
            _env_file=None,
            scrape_cdp_url="http://host.docker.internal:9222",
            cdp_allow_docker_host=False,
        )
