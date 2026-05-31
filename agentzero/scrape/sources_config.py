"""Load optional ``docs/examples/job_sources.json`` for custom boards + JobSpy site lists.

The live five-source stack is fixed in ``agentzero/scrape/factory.py`` and configured via
``.env``. This module and ``parse_list.py`` remain **reference / example-only** for future
custom ``list_pages`` boards — not wired into ``run_scrape.py`` today.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import BaseModel, Field

from agentzero.scrape.resilience import JOBSPY_SITE_NAMES

DEFAULT_JOB_SOURCES_PATH = Path("docs/examples/job_sources.json")


class JobSourceSelectors(BaseModel):
    """CSS selectors for ``list_pages`` scraping."""

    job_card: str = "article, li, div[class*='job']"
    title_link: str = "a[href]"
    company: str = "[class*='company'], .company"
    location: str = "[class*='location'], .location"


class JobSourceEntry(BaseModel):
    name: str
    url: str
    type: str = "general"
    description: str | None = None
    search_keywords: list[str] = Field(default_factory=list)
    scrape_strategy: Literal["list_pages", "jobspy", "browser_indeed"] = "list_pages"
    priority: Literal["high", "medium", "low"] = "medium"
    search_url_template: str | None = None
    selectors: JobSourceSelectors = Field(default_factory=JobSourceSelectors)
    enabled: bool = True

    @property
    def slug(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_")
        return slug or "custom"

    def build_search_url(self, *, query: str, location: str) -> str:
        template = self.search_url_template or self.url
        return (
            template.replace("{query}", quote_plus(query))
            .replace("{location}", quote_plus(location))
            .replace("{q}", quote_plus(query))
            .replace("{l}", quote_plus(location))
        )


class ScrapeSettingsBlock(BaseModel):
    max_jobs_per_source: int | None = None
    refresh_interval_hours: int | None = None
    respect_robots_txt: bool = True
    use_proxies: bool = False


class JobSourcesFile(BaseModel):
    job_sources: list[JobSourceEntry] = Field(default_factory=list)
    jobspy_sites: list[str] = Field(default_factory=list)
    default_search_terms: list[str] = Field(default_factory=list)
    scrape_settings: ScrapeSettingsBlock | None = None

    def list_pages_sources(self) -> list[JobSourceEntry]:
        return [
            entry
            for entry in self.job_sources
            if entry.enabled and entry.scrape_strategy == "list_pages"
        ]

    def jobspy_site_names(self) -> list[str]:
        names: list[str] = []
        for entry in self.job_sources:
            if entry.enabled and entry.scrape_strategy == "jobspy":
                slug = entry.slug
                if slug in JOBSPY_SITE_NAMES and slug not in names:
                    names.append(slug)
        for site in self.jobspy_sites:
            cleaned = site.strip().lower()
            if cleaned in JOBSPY_SITE_NAMES and cleaned not in names:
                names.append(cleaned)
        return names


def load_job_sources(path: Path | None = None) -> JobSourcesFile | None:
    """Parse ``docs/examples/job_sources.json`` when present."""
    cfg_path = path or DEFAULT_JOB_SOURCES_PATH
    if not cfg_path.is_file():
        return None
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    return JobSourcesFile.model_validate(data)


@lru_cache(maxsize=8)
def cached_job_sources(path_str: str) -> JobSourcesFile | None:
    return load_job_sources(Path(path_str))


def clear_job_sources_cache() -> None:
    cached_job_sources.cache_clear()


def resolve_jobspy_sites(
    configured: list[str],
    *,
    job_sources: JobSourcesFile | None,
) -> list[str]:
    """Merge env/config JobSpy sites with optional JSON list; support ``all``."""
    sites: list[str] = []
    for site in configured:
        cleaned = site.strip().lower()
        if not cleaned:
            continue
        if cleaned == "all":
            sites.extend(sorted(JOBSPY_SITE_NAMES))
            continue
        if cleaned in JOBSPY_SITE_NAMES:
            sites.append(cleaned)

    if job_sources is not None:
        for site in job_sources.jobspy_site_names():
            if site not in sites:
                sites.append(site)

    # Preserve order, dedupe.
    seen: set[str] = set()
    ordered: list[str] = []
    for site in sites:
        if site not in seen:
            ordered.append(site)
            seen.add(site)
    return ordered
