"""Build the configured scrape source stack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentzero.scrape.base import JobSource
from agentzero.scrape.browser_board import BrowserJobBoardSource
from agentzero.scrape.browser_common import primary_scrape_query
from agentzero.scrape.jobspy_source import JobSpySource
from agentzero.scrape.multi import MultiSource

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.llm.provider import LLMProvider

# Fixed production stack: browser first, then JobSpy HTTP (sequential with delay).
CORE_BROWSER_SITES = ("indeed", "linkedin", "glassdoor")
CORE_JOBSPY_SITES = ("google", "zip_recruiter")


def _normalize_site_list(sites: list[str]) -> set[str]:
    return {s.strip().lower() for s in sites if s.strip()}


def resolve_core_jobspy_sites(scrape_sites: list[str]) -> list[str]:
    """JobSpy sites from env intersected with the allowed core list."""
    configured = _normalize_site_list(scrape_sites)
    return [site for site in CORE_JOBSPY_SITES if site in configured]


def build_scrape_source(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
) -> JobSource:
    """Return the five-source stack: Indeed, LinkedIn, Glassdoor (browser) + Google, ZipRecruiter (JobSpy)."""
    from agentzero.config import get_settings
    from agentzero.ingest.search_profile import get_effective_settings

    cfg = settings or get_settings()
    if llm is not None:
        cfg = get_effective_settings(cfg, llm=llm)

    browser_enabled = _normalize_site_list(cfg.scrape_browser_sites)
    jobspy_sites = resolve_core_jobspy_sites(cfg.scrape_sites)

    sources: list[JobSource] = []

    for site in CORE_BROWSER_SITES:
        if site in browser_enabled:
            sources.append(BrowserJobBoardSource(cfg, site=site))

    if jobspy_sites:
        jobspy_cfg = cfg.model_copy(update={"scrape_sites": jobspy_sites})
        sources.append(JobSpySource(jobspy_cfg, llm=llm))

    if not sources:
        raise ValueError(
            "No scrape sources configured. Set AGENTZERO_SCRAPE_BROWSER_SITES "
            "(indeed, linkedin, glassdoor) and/or AGENTZERO_SCRAPE_SITES "
            "(google, zip_recruiter) in .env."
        )

    if len(sources) == 1:
        return sources[0]
    return MultiSource(sources)


def list_source_names(source: JobSource) -> list[str]:
    """Return human-readable source names for logging."""
    if isinstance(source, MultiSource):
        return [s.name for s in source._sources]
    return [source.name]


def describe_scrape_stack(source: JobSource, settings: Settings) -> dict[str, Any]:
    """Summary for run_scrape startup banner."""
    term, parsed = primary_scrape_query(settings)
    jobspy: list[str] = []
    if isinstance(source, MultiSource):
        for s in source._sources:
            if s.name == "jobspy":
                jobspy = list(s.settings.scrape_sites)  # type: ignore[attr-defined]
    elif source.name == "jobspy":
        jobspy = list(source.settings.scrape_sites)  # type: ignore[attr-defined]

    return {
        "sources": list_source_names(source),
        "primary_term": term,
        "primary_location": parsed.jobspy_location,
        "primary_location_raw": parsed.raw,
        "remote": parsed.is_remote,
        "jobspy_sites": jobspy,
        "primary_query_only": settings.scrape_primary_query_only,
        "delay_seconds": settings.scrape_delay_seconds,
    }
