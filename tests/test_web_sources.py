from agentzero.config import Settings
from agentzero.web.operator_config import OperatorScrapeConfig
from agentzero.web.sources import active_source_names, source_catalog


def test_source_catalog_three_browser_boards_only():
    settings = Settings(_env_file=None)
    rows = source_catalog(settings, None)
    assert len(rows) == 3
    assert {r.id for r in rows} == {"indeed", "linkedin", "glassdoor"}
    assert all(r.group == "browser" for r in rows)
    assert all(r.enabled for r in rows)


def test_source_catalog_has_no_jobspy_rows():
    settings = Settings(
        _env_file=None,
        scrape_sites=["google", "zip_recruiter"],
    )
    rows = source_catalog(settings, None)
    assert not any(r.group == "jobspy" for r in rows)


def test_source_catalog_orders_cdp_sites_last():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        scrape_cdp_url="http://127.0.0.1:9222",
        scrape_cdp_sites=["indeed", "glassdoor"],
    )
    rows = source_catalog(settings, None)
    ids = [r.id for r in rows]
    assert ids.index("linkedin") < ids.index("indeed")
    assert ids.index("indeed") < ids.index("glassdoor")


def test_source_catalog_respects_operator_overlay():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
    )
    op = OperatorScrapeConfig(scrape_browser_sites=["glassdoor"], scrape_sites=["google"])
    rows = source_catalog(settings, op)
    by_id = {r.id: r.enabled for r in rows}
    assert by_id["indeed"] is False
    assert by_id["glassdoor"] is True
    assert by_id["linkedin"] is False


def test_active_source_names():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed"],
        scrape_sites=[],
    )
    names = active_source_names(settings, None)
    assert any("indeed" in n for n in names)
    assert not any("linkedin" in n for n in names)
