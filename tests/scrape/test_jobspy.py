from types import SimpleNamespace

import pandas as pd
import pytest

from agentzero.config import Settings
from agentzero.scrape.jobspy_params import build_jobspy_scrape_kwargs
from agentzero.scrape.jobspy_source import JobSpySource, row_to_raw_record
from agentzero.scrape.location import (
    parse_locations_for_scrape,
    parse_search_location,
)


def test_row_to_raw_record_maps_jobspy_columns():
    row = {
        "title": "Engineer",
        "company": "Acme",
        "job_url": "https://jobs.example.com/1",
        "site": "indeed",
        "min_amount": 100000,
        "company_rating": 4.2,
    }
    raw = row_to_raw_record(row, default_source="jobspy")
    assert raw["title"] == "Engineer"
    assert raw["url"] == "https://jobs.example.com/1"
    assert raw["source"] == "indeed"
    assert raw["comp_min"] == 100000
    assert raw["glassdoor_rating"] == 4.2


def test_parse_remote_usa_location():
    parsed = parse_search_location("remote - usa", default_country="USA")
    assert parsed.jobspy_location == "United States"
    assert parsed.is_remote is True
    assert parsed.omit_hours_old is True


def test_parse_remote_dedupes_with_bare_remote():
    parsed = parse_locations_for_scrape(["remote", "remote - usa"], default_country="USA")
    assert len(parsed) == 1
    assert parsed[0].is_remote is True


def test_build_jobspy_kwargs_indeed_remote_omits_hours_old():
    settings = Settings(_env_file=None, hours_old=168, country_indeed="USA")
    parsed = parse_search_location("Remote - USA")
    kwargs = build_jobspy_scrape_kwargs(
        settings,
        site="indeed",
        term="Security Engineer",
        parsed=parsed,
    )
    assert kwargs["location"] == "United States"
    assert kwargs["is_remote"] is True
    assert kwargs["hours_old"] is None
    assert kwargs["country_indeed"] == "USA"


def test_build_jobspy_kwargs_city_keeps_hours_old():
    settings = Settings(_env_file=None, hours_old=168, country_indeed="USA")
    parsed = parse_search_location("Los Angeles, CA")
    kwargs = build_jobspy_scrape_kwargs(
        settings,
        site="indeed",
        term="Security Engineer",
        parsed=parsed,
    )
    assert kwargs["location"] == "Los Angeles, CA"
    assert "is_remote" not in kwargs
    assert kwargs["hours_old"] == 168


def test_jobspy_source_fetch_uses_injected_scraper():
    captured: list[dict] = []

    def fake_scrape_jobs(**kwargs):
        captured.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "title": "Backend Dev",
                    "company": "Co",
                    "job_url": "https://x.com/1",
                    "site": "indeed",
                }
            ]
        )

    source = JobSpySource(
        settings=SimpleNamespace(
            search_terms=["engineer", "architect"],
            locations=["remote - usa"],
            results_wanted=5,
            hours_old=72,
            country_indeed="USA",
            remote_preferred=True,
            proxies=[],
            scrape_sites=["google", "zip_recruiter"],
            scrape_user_agent=None,
            scrape_delay_seconds=0,
            scrape_verbose=0,
            linkedin_fetch_description=False,
            scrape_primary_query_only=True,
        ),
        scraper=fake_scrape_jobs,
    )
    records = source.fetch()
    assert len(records) == 2
    assert len(captured) == 2
    assert captured[0]["location"] == "United States"
    assert captured[0]["is_remote"] is True
    assert all(c["search_term"] == "engineer" for c in captured)


def test_jobspy_import_error_when_scraper_missing(monkeypatch):
    source = JobSpySource(
        settings=SimpleNamespace(
            search_terms=["x"],
            locations=["Remote"],
            results_wanted=1,
            hours_old=1,
            country_indeed="USA",
            remote_preferred=False,
            proxies=[],
            scrape_sites=["indeed"],
            scrape_user_agent=None,
            scrape_delay_seconds=0,
            scrape_verbose=0,
            linkedin_fetch_description=False,
        ),
        scraper=None,
    )
    def _raise_import() -> None:
        raise ImportError("no jobspy")

    monkeypatch.setattr(source, "_import_scrape_jobs", _raise_import)
    with pytest.raises(ImportError, match="no jobspy"):
        source.fetch()
