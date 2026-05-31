"""JobSpy-backed multi-board scraper (Indeed, LinkedIn, Glassdoor, etc.)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentzero.config import Settings, get_settings
from agentzero.ingest.resume import RESUME_DIR
from agentzero.models import RawRecord
from agentzero.scrape.base import JobSource
from agentzero.scrape.jobspy_params import build_jobspy_scrape_kwargs, iter_scrape_queries
from agentzero.scrape.resilience import JOBSPY_SITE_NAMES
from agentzero.scrape.sources_config import resolve_jobspy_sites

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

log = logging.getLogger(__name__)

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
        llm: LLMProvider | None = None,
        resume_dir: Path = RESUME_DIR,
    ) -> None:
        self._base_settings = settings or get_settings()
        self._scraper = scraper
        self._llm = llm
        self._resume_dir = resume_dir

    def _active_settings(self) -> Settings:
        if self._llm is None:
            return self._base_settings
        from agentzero.ingest.search_profile import get_effective_settings

        return get_effective_settings(
            self._base_settings,
            llm=self._llm,
            resume_dir=self._resume_dir,
        )

    @property
    def settings(self) -> Settings:
        """Latest settings including résumé-derived search terms (when LLM is configured)."""
        return self._active_settings()

    def fetch(self) -> Sequence[RawRecord]:
        settings = self._active_settings()
        scrape_fn = self._scraper or self._import_scrape_jobs()
        sites = [
            s
            for s in resolve_jobspy_sites(settings.scrape_sites, job_sources=None)
            if s in JOBSPY_SITE_NAMES
        ]
        if not sites:
            log.warning("No valid JobSpy sites configured; skipping JobSpy fetch")
            return []

        frames = []
        delay = settings.scrape_delay_seconds

        for term, parsed in iter_scrape_queries(settings):
            for site in sites:
                print(
                    f"[JobSpy/{site}] Fetching {term!r} @ {parsed.jobspy_location}…",
                    flush=True,
                )
                try:
                    kwargs = build_jobspy_scrape_kwargs(
                        settings,
                        site=site,
                        term=term,
                        parsed=parsed,
                    )
                    df = scrape_fn(**kwargs)
                    if df is not None and len(df) > 0:
                        frames.append(df)
                        log.info(
                            "JobSpy %s: %d rows for %r @ %r (remote=%s)",
                            site,
                            len(df),
                            term,
                            parsed.raw,
                            parsed.is_remote,
                        )
                    else:
                        log.warning(
                            "JobSpy %s: 0 rows for %r @ %r (remote=%s)",
                            site,
                            term,
                            parsed.raw,
                            parsed.is_remote,
                        )
                except Exception as exc:
                    log.warning(
                        "JobSpy %s failed for %r @ %r: %s",
                        site,
                        term,
                        parsed.raw,
                        exc,
                    )
                if delay > 0:
                    time.sleep(delay)

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
