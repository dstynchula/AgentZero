"""Tests for LinkedIn/Glassdoor browser parsers and five-source factory."""

from __future__ import annotations

from pathlib import Path

from agentzero.config import Settings
from agentzero.scrape.browser_linkedin import (
    build_linkedin_search_url,
    parse_linkedin_search_html,
)
from agentzero.scrape.factory import (
    CORE_BROWSER_SITES,
    CORE_JOBSPY_SITES,
    build_scrape_source,
    describe_scrape_stack,
    resolve_core_jobspy_sites,
)
from agentzero.scrape.location import parse_search_location
from agentzero.scrape.multi import MultiSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_linkedin_search_html():
    html = (FIXTURES / "linkedin_search.html").read_text(encoding="utf-8")
    records = parse_linkedin_search_html(html)
    assert len(records) == 2
    assert records[0]["title"] == "Staff Security Engineer"
    assert records[0]["company"] == "Acme Corp"
    assert records[0]["remote"] is True


def test_parse_linkedin_search_spa_html():
    from agentzero.scrape.browser_linkedin import page_has_job_results

    html = (FIXTURES / "linkedin_search_spa.html").read_text(encoding="utf-8")
    assert page_has_job_results(html)
    records = parse_linkedin_search_html(html)
    assert len(records) == 2
    garner = next(r for r in records if r["company"] == "Garner Health")
    assert garner["title"] == "Staff Security Engineer"
    assert garner["url"] == "https://www.linkedin.com/jobs/view/4328174567"
    assert garner["location"] == "United States (Remote)"
    assert garner["remote"] is True
    assert garner["comp_raw"] == "$239K/yr - $275K/yr"
    principal = next(r for r in records if r["company"] == "Acme Corp")
    assert principal["title"] == "Principal Security Engineer"
    assert principal["url"].endswith("9876543210")


def test_parse_linkedin_search_embedded_only_html():
    html = (FIXTURES / "linkedin_search_embedded_only.html").read_text(encoding="utf-8")
    records = parse_linkedin_search_html(html)
    assert len(records) == 3
    by_company = {r["company"]: r for r in records}
    assert by_company["Rippling"]["title"] == "Lead Security Engineer"
    assert by_company["Rippling"]["location"] == "United States (Remote)"
    from agentzero.scrape.validate import validate_raw

    rippling_raw = by_company["Rippling"]
    assert rippling_raw.get("comp_raw") == "$200K/yr - $240K/yr"
    rippling = validate_raw(rippling_raw, source="linkedin").job
    assert rippling is not None
    assert rippling.comp_min == 200_000
    assert rippling.comp_max is not None
    assert rippling.comp_max >= rippling.comp_min
    assert by_company["EvenUp"]["title"] == "Lead Security Engineer"
    assert by_company["Harvey"]["title"] == "Staff Cloud Security Engineer"


def test_build_linkedin_remote_url():
    parsed = parse_search_location("remote - usa")
    url = build_linkedin_search_url(term="Security Engineer", parsed=parsed)
    assert "keywords=Security" in url
    assert "f_WT=2" in url


def test_resolve_core_jobspy_sites():
    assert resolve_core_jobspy_sites(["google"]) == ["google"]
    assert resolve_core_jobspy_sites(["google", "zip_recruiter", "linkedin"]) == [
        "google",
        "zip_recruiter",
    ]


def test_factory_five_source_stack():
    settings = Settings(
        _env_file=None,
        scrape_sites=["google", "zip_recruiter"],
        scrape_browser_sites=list(CORE_BROWSER_SITES),
        search_terms=["Staff Security Engineer", "Principal Security Engineer"],
        locations=["remote - usa"],
        remote_preferred=True,
        scrape_primary_query_only=True,
    )
    source = build_scrape_source(settings)
    assert isinstance(source, MultiSource)
    names = [s.name for s in source._sources]
    assert names == [
        "indeed_browser",
        "linkedin_browser",
        "glassdoor_browser",
        "jobspy",
    ]
    jobspy = source._sources[-1]
    assert jobspy.settings.scrape_sites == list(CORE_JOBSPY_SITES)


def test_describe_scrape_stack():
    settings = Settings(
        _env_file=None,
        scrape_sites=["google", "zip_recruiter"],
        scrape_browser_sites=["indeed"],
        search_terms=["Security Engineer"],
        locations=["remote - usa"],
        remote_preferred=True,
    )
    source = build_scrape_source(settings)
    info = describe_scrape_stack(source, settings)
    assert info["primary_term"] == "Security Engineer"
    assert info["remote"] is True
    assert "indeed_browser" in info["sources"]
