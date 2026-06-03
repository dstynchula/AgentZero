from pathlib import Path

from agentzero.config import Settings
from agentzero.web.operator_config import (
    OperatorScrapeConfig,
    effective_scrape_lists,
    load_operator_config,
    normalize_source_selection,
    operator_config_path,
    save_operator_config,
    settings_for_scrape,
)


def test_operator_config_round_trip(tmp_path: Path):
    path = tmp_path / "data" / "web_operator_config.json"
    cfg = OperatorScrapeConfig(scrape_browser_sites=["indeed"], scrape_sites=["google"])
    save_operator_config(path, cfg)
    loaded = load_operator_config(path)
    assert loaded == cfg


def test_effective_lists_overlay():
    base = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        scrape_sites=["google", "zip_recruiter"],
    )
    op = OperatorScrapeConfig(scrape_browser_sites=["linkedin"], scrape_sites=[])
    browser, jobspy = effective_scrape_lists(base, op)
    assert browser == ["linkedin"]
    assert jobspy == []


def test_normalize_rejects_unknown_sites():
    cfg = normalize_source_selection(["indeed", "bogus"], ["zip_recruiter", "evil"])
    assert cfg.scrape_browser_sites == ["indeed"]
    assert cfg.scrape_sites == []


def test_settings_for_scrape_disables_interactive():
    base = Settings(_env_file=None, search_interactive=True)
    merged = settings_for_scrape(base, None)
    assert merged.search_interactive is False


def test_operator_config_path_beside_db(tmp_path: Path):
    db = tmp_path / "data" / "agentzero.db"
    assert operator_config_path(db) == tmp_path / "data" / "web_operator_config.json"
