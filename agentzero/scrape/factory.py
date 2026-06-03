"""Build the configured scrape source stack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentzero.scrape.base import JobSource
from agentzero.scrape.browser_board import BrowserJobBoardSource
from agentzero.scrape.browser_common import primary_scrape_query
from agentzero.scrape.multi import MultiSource

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.llm.provider import LLMProvider

# Production stack: Playwright/CDP for Indeed, LinkedIn, and Glassdoor only.
CORE_BROWSER_SITES = ("indeed", "linkedin", "glassdoor")


def _normalize_site_list(sites: list[str]) -> set[str]:
    return {s.strip().lower() for s in sites if s.strip()}


def build_scrape_source(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
) -> JobSource:
    """Return browser sources for Indeed, LinkedIn, and Glassdoor (enabled via env)."""
    from agentzero.config import get_settings
    from agentzero.ingest.search_profile import get_effective_settings

    _ = llm  # reserved for search-profile merge via get_effective_settings
    cfg = settings or get_settings()
    if llm is not None:
        cfg = get_effective_settings(cfg, llm=llm)

    browser_enabled = _normalize_site_list(cfg.scrape_browser_sites)
    sources: list[JobSource] = []

    for site in CORE_BROWSER_SITES:
        if site not in browser_enabled:
            continue
        if site == "linkedin":
            from agentzero.scrape.linkedin_source import LinkedInJobSource

            sources.append(LinkedInJobSource(cfg))
        else:
            sources.append(BrowserJobBoardSource(cfg, site=site))

    if not sources:
        raise ValueError(
            "No scrape sources configured. Set AGENTZERO_SCRAPE_BROWSER_SITES "
            "to one or more of: indeed, linkedin, glassdoor."
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
    return {
        "sources": list_source_names(source),
        "primary_term": term,
        "primary_location": parsed.jobspy_location,
        "primary_location_raw": parsed.raw,
        "remote": parsed.is_remote,
        "primary_query_only": settings.scrape_primary_query_only,
        "delay_seconds": settings.scrape_delay_seconds,
    }
