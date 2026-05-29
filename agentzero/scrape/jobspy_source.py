"""JobSpy-backed multi-board scraper (Indeed, LinkedIn, Glassdoor, etc.)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from agentzero.config import Settings, get_settings
from agentzero.models import RawRecord
from agentzero.scrape.base import JobSource

# Map JobSpy dataframe columns to RawRecord keys.
JOBSPY_COLUMN_MAP = {
    "title": "title",
    "company": "company",
    "job_url": "url",
    "location": "location",
    "is_remote": "remote",
    "min_amount": "comp_min",
    "max_amount": "comp_max",
    "currency": "currency",
    "company_rating": "glassdoor_rating",
    "company_reviews_count": "glassdoor_reviews",
    "description": "description",
    "date_posted": "date_posted",
    "site": "source",
}


def row_to_raw_record(row: dict[str, Any], *, default_source: str) -> RawRecord:
    """Convert a JobSpy DataFrame row dict into a ``RawRecord``."""
    raw: RawRecord = {}
    for jobspy_key, canonical_key in JOBSPY_COLUMN_MAP.items():
        if jobspy_key in row and row[jobspy_key] is not None:
            value = row[jobspy_key]
            if hasattr(value, "item"):  # numpy scalar
                value = value.item()
            raw[canonical_key] = value
    if not raw.get("source"):
        raw["source"] = str(row.get("site") or default_source)
    if not raw.get("url") and row.get("job_url"):
        raw["url"] = str(row["job_url"])
    return raw


class JobSpySource(JobSource):
    """Fetch jobs via ``python-jobspy`` (network or injected scraper for tests)."""

    name = "jobspy"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        scraper: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._scraper = scraper

    def fetch(self) -> Sequence[RawRecord]:
        scrape_fn = self._scraper or self._import_scrape_jobs()
        frames = []
        for term in self.settings.search_terms:
            for location in self.settings.locations:
                df = scrape_fn(
                    site_name=[
                        "indeed",
                        "linkedin",
                        "glassdoor",
                        "zip_recruiter",
                        "google",
                    ],
                    search_term=term,
                    location=location,
                    results_wanted=self.settings.results_wanted,
                    hours_old=self.settings.hours_old,
                    country_indeed=self.settings.country_indeed,
                    proxies=self.settings.proxies or None,
                )
                frames.append(df)
        if not frames:
            return []
        import pandas as pd

        combined = pd.concat(frames, ignore_index=True)
        records: list[RawRecord] = []
        for row in combined.to_dict(orient="records"):
            records.append(row_to_raw_record(row, default_source=self.name))
        return records

    @staticmethod
    def _import_scrape_jobs() -> Callable[..., Any]:
        try:
            from jobspy import scrape_jobs
        except ImportError as exc:
            raise ImportError(
                "JobSpy source requires python-jobspy. "
                "Install with: pip install -e '.[scrape]'"
            ) from exc
        return scrape_jobs
