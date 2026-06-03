import importlib.util

from agentzero.config import Settings
from agentzero.scrape.factory import CORE_BROWSER_SITES, build_scrape_source, list_source_names


def test_jobspy_source_module_removed():
    assert importlib.util.find_spec("agentzero.scrape.jobspy_source") is None


def test_build_scrape_source_only_browser_boards():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        scrape_sites=["google", "zip_recruiter"],
    )
    source = build_scrape_source(settings)
    names = list_source_names(source)
    assert "jobspy" not in names
    assert all(any(site in n for site in CORE_BROWSER_SITES) for n in names)
    assert len(names) == 3


def test_build_scrape_source_ignores_legacy_jobspy_env():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed"],
        scrape_sites=["google"],
    )
    names = list_source_names(build_scrape_source(settings))
    assert names == ["indeed_browser"]
