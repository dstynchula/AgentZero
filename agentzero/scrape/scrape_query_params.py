"""Build scrape query parameters from AgentZero settings + parsed locations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentzero.scrape.location import ParsedLocation
from agentzero.scrape.remote_policy import parse_locations_for_scrape_remote_aware
from agentzero.scrape.resilience import DEFAULT_USER_AGENT

if TYPE_CHECKING:
    from agentzero.config import Settings


def build_scrape_query_kwargs(
    settings: Settings,
    *,
    site: str,
    term: str,
    parsed: ParsedLocation,
) -> dict[str, Any]:
    """Return location/search kwargs for one board query (browser or legacy HTTP)."""
    kwargs: dict[str, Any] = {
        "site_name": [site],
        "search_term": term,
        "location": parsed.jobspy_location,
        "results_wanted": settings.results_wanted,
        "country_indeed": parsed.country_indeed,
        "proxies": settings.proxies or None,
        "user_agent": settings.scrape_user_agent or DEFAULT_USER_AGENT,
        "linkedin_fetch_description": settings.linkedin_fetch_description,
        "verbose": settings.scrape_verbose,
    }

    if parsed.is_remote:
        kwargs["is_remote"] = True

    if site == "indeed" and parsed.omit_hours_old:
        kwargs["hours_old"] = None
    else:
        kwargs["hours_old"] = settings.hours_old

    return kwargs


# Back-compat alias for callers not yet renamed.
build_jobspy_scrape_kwargs = build_scrape_query_kwargs


def iter_scrape_queries(settings: Settings) -> list[tuple[str, ParsedLocation]]:
    """One primary query or full term x location expansion."""
    from agentzero.scrape.browser_common import primary_scrape_query

    if getattr(settings, "scrape_primary_query_only", True):
        term, parsed = primary_scrape_query(settings)
        return [(term, parsed)]

    parsed_locations = parse_locations_for_scrape_remote_aware(settings)
    return [
        (term, parsed)
        for term in settings.search_terms
        for parsed in parsed_locations
    ]
