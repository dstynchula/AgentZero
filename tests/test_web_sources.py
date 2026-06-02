from agentzero.config import Settings
from agentzero.web.operator_config import OperatorScrapeConfig
from agentzero.web.sources import active_source_names, source_catalog


def test_source_catalog_all_enabled_by_default():
    settings = Settings(_env_file=None)
    rows = source_catalog(settings, None)
    assert len(rows) == 5
    by_id = {r.id: r.enabled for r in rows}
    assert by_id["linkedin"] is True
    assert by_id["google"] is True
    assert by_id["zip_recruiter"] is True
    assert by_id["indeed"] is False
    assert by_id["glassdoor"] is False


def test_source_catalog_orders_cdp_sites_last():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        scrape_sites=["google", "zip_recruiter"],
        scrape_cdp_url="http://127.0.0.1:9222",
        scrape_cdp_sites=["indeed", "glassdoor"],
    )
    rows = source_catalog(settings, None)
    ids = [r.id for r in rows]
    assert ids.index("linkedin") < ids.index("google")
    assert ids.index("zip_recruiter") < ids.index("indeed")
    assert ids.index("indeed") < ids.index("glassdoor")


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
