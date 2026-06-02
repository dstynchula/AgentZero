from agentzero.config import Settings
from agentzero.web.operator_config import OperatorScrapeConfig
from agentzero.web.sources import active_source_names, source_catalog


def test_source_catalog_all_enabled_by_default():
    settings = Settings(_env_file=None)
    rows = source_catalog(settings, None)
    assert len(rows) == 5
    assert all(r.enabled for r in rows)


def test_source_catalog_respects_operator_overlay():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        scrape_sites=["google", "zip_recruiter"],
    )
    op = OperatorScrapeConfig(scrape_browser_sites=["glassdoor"], scrape_sites=[])
    rows = source_catalog(settings, op)
    by_id = {r.id: r.enabled for r in rows}
    assert by_id["indeed"] is False
    assert by_id["glassdoor"] is True
    assert by_id["google"] is True


def test_active_source_names():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed"],
        scrape_sites=[],
    )
    names = active_source_names(settings, None)
    assert any("indeed" in n for n in names)
    assert not any("linkedin" in n for n in names)
