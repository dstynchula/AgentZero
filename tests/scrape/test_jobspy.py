from types import SimpleNamespace

import pandas as pd
import pytest

from agentzero.scrape.jobspy_source import JobSpySource, row_to_raw_record


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


def test_jobspy_source_fetch_uses_injected_scraper():
    df = pd.DataFrame(
        [
            {
                "title": "Backend Dev",
                "company": "Co",
                "job_url": "https://x.com/1",
                "site": "linkedin",
            }
        ]
    )

    def fake_scrape_jobs(**kwargs):
        return df

    source = JobSpySource(
        settings=SimpleNamespace(
            search_terms=["engineer"],
            locations=["Remote"],
            results_wanted=5,
            hours_old=72,
            country_indeed="USA",
            proxies=[],
        ),
        scraper=fake_scrape_jobs,
    )
    records = source.fetch()
    assert len(records) == 1
    assert records[0]["title"] == "Backend Dev"


def test_jobspy_import_error_when_scraper_missing(monkeypatch):
    source = JobSpySource(
        settings=SimpleNamespace(
            search_terms=["x"],
            locations=["Remote"],
            results_wanted=1,
            hours_old=1,
            country_indeed="USA",
            proxies=[],
        ),
        scraper=None,
    )
    def _raise_import() -> None:
        raise ImportError("no jobspy")

    monkeypatch.setattr(source, "_import_scrape_jobs", _raise_import)
    with pytest.raises(ImportError, match="no jobspy"):
        source.fetch()
