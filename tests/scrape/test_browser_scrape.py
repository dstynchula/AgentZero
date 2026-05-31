from pathlib import Path

from agentzero.config import Settings
from agentzero.scrape.browser_indeed import (
    extract_mosaic_payload,
    mosaic_results_to_records,
    page_has_job_results,
    page_needs_human,
    parse_indeed_mosaic_html,
    parse_indeed_search_html,
)
from agentzero.scrape.factory import build_scrape_source
from agentzero.scrape.jobspy_source import JobSpySource
from agentzero.scrape.multi import MultiSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_indeed_search_html():
    html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    records = parse_indeed_search_html(html)
    assert len(records) == 2
    assert records[0]["title"] == "Staff Security Engineer"
    assert records[0]["company"] == "Acme Corp"
    assert records[0]["url"].startswith("https://www.indeed.com/")
    assert records[0]["location"] == "Remote"


def test_page_needs_human_detects_captcha():
    assert page_needs_human("<html>verify you are human</html>")
    assert page_needs_human("", "https://www.indeed.com/sorry/Index")
    assert not page_needs_human("<html>job_seen_beacon</html>", "https://www.indeed.com/jobs")


def test_page_has_job_results():
    html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    assert page_has_job_results(html)
    assert page_has_job_results("<div class='jobsearch-NoResults'></div>")
    mosaic = (FIXTURES / "indeed_mosaic.html").read_text(encoding="utf-8")
    assert page_has_job_results(mosaic)


def test_parse_indeed_mosaic_html():
    html = (FIXTURES / "indeed_mosaic.html").read_text(encoding="utf-8")
    records = parse_indeed_mosaic_html(html)
    assert len(records) == 2
    assert records[0]["title"] == "Staff Security Engineer"
    assert records[0]["company"] == "Acme Corp"
    assert records[0]["comp_raw"] == "$180,000 - $220,000 a year"
    assert records[0]["glassdoor_rating"] == 4.2
    assert records[1]["remote"] is True


def test_page_needs_human_false_when_mosaic_jobs_present():
    html = (FIXTURES / "indeed_mosaic.html").read_text(encoding="utf-8")
    assert not page_needs_human(html)


def test_extract_mosaic_payload_roundtrip():
    html = (FIXTURES / "indeed_mosaic.html").read_text(encoding="utf-8")
    payload = extract_mosaic_payload(html)
    assert payload is not None
    records = mosaic_results_to_records(payload)
    assert len(records) == 2


def test_mosaic_remote_search_trusts_city_on_remote_query():
    payload = {
        "metaData": {
            "mosaicProviderJobCardsModel": {
                "results": [
                    {
                        "displayTitle": "Staff Security Engineer",
                        "company": "Garner Health",
                        "formattedLocation": "New York, NY",
                        "jobkey": "garner1",
                    },
                    {
                        "displayTitle": "Security Engineer",
                        "company": "Acme",
                        "formattedLocation": "Hybrid - Boston, MA",
                        "jobkey": "hybrid1",
                    },
                ]
            }
        }
    }
    records = mosaic_results_to_records(payload, remote_search=True)
    assert records[0]["remote"] is True
    assert records[1]["remote"] is False


def test_jobspy_fetch_calls_sites_sequentially():
    calls: list[str] = []

    def fake_scrape(**kwargs):
        site = kwargs["site_name"][0]
        calls.append(site)
        import pandas as pd

        return pd.DataFrame(
            [{"title": "Job", "company": "Co", "job_url": "https://x.com/1", "site": site}]
        )

    settings = Settings(
        _env_file=None,
        search_terms=["engineer"],
        locations=["Remote"],
        scrape_sites=["google", "indeed"],
        scrape_browser_sites=[],
        results_wanted=5,
        hours_old=72,
        country_indeed="usa",
        scrape_delay_seconds=0,
    )
    source = JobSpySource(settings=settings, scraper=fake_scrape)
    records = source.fetch()
    assert calls == ["google", "indeed"]
    assert len(records) == 2


def test_build_scrape_source_combines_browser_and_jobspy():
    settings = Settings(
        _env_file=None,
        scrape_sites=["google", "zip_recruiter"],
        scrape_browser_sites=["indeed"],
        search_terms=["x"],
        locations=["Remote"],
    )
    source = build_scrape_source(settings)
    assert isinstance(source, MultiSource)
    assert len(source._sources) == 2


def test_build_scrape_source_jobspy_only():
    settings = Settings(
        _env_file=None,
        scrape_sites=["google", "zip_recruiter"],
        scrape_browser_sites=[],
        search_terms=["x"],
        locations=["Remote"],
    )
    source = build_scrape_source(settings)
    from agentzero.scrape.jobspy_source import JobSpySource

    assert isinstance(source, JobSpySource)


def test_build_scrape_source_no_list_pages():
    settings = Settings(
        _env_file=None,
        scrape_sites=["google"],
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        search_terms=["x"],
        locations=["Remote"],
    )
    source = build_scrape_source(settings)
    assert isinstance(source, MultiSource)
    names = {type(s).__name__ for s in source._sources}
    assert "ListPagesBrowserSource" not in names


def test_build_scrape_source_raises_when_empty():
    settings = Settings(
        _env_file=None,
        scrape_sites=[],
        scrape_browser_sites=[],
        search_terms=["x"],
        locations=["Remote"],
    )
    import pytest

    with pytest.raises(ValueError, match="No scrape sources configured"):
        build_scrape_source(settings)
