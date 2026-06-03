"""Normalize user location strings for Indeed / JobSpy remote searches."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Collapse "remote - usa", "remote, USA", "Remote US", etc. into one remote-US query.
_REMOTE_US_RE = re.compile(
    r"^remote(?:\s*[-–—,]\s*(?:usa|u\.?s\.?a?\.?|united\s+states))?$|"
    r"^(?:usa|u\.?s\.?a?\.?|united\s+states)\s*[-–—,]\s*remote$|"
    r"^(?:wfh|work\s+from\s+home)(?:\s*[-–—,]\s*(?:usa|u\.?s\.?a?\.?|united\s+states))?$",
    re.IGNORECASE,
)
_REMOTE_CA_RE = re.compile(
    r"^remote(?:\s*[-–—,]\s*(?:canada|ca))?$|"
    r"^canada\s*[-–—,]\s*remote$",
    re.IGNORECASE,
)
_REMOTE_SEPARATORS = "-–—,"
_MAX_REMOTE_REGION_LEN = 80


def _remote_generic_region(normalized: str) -> str | None:
    """Parse ``remote`` / ``remote - region`` without a backtracking-prone regex."""
    lower = normalized.casefold()
    if not lower.startswith("remote"):
        return None
    suffix = normalized[6:].lstrip()
    if not suffix:
        return ""
    if suffix[0] in _REMOTE_SEPARATORS:
        suffix = suffix[1:].lstrip()
    region = suffix[:_MAX_REMOTE_REGION_LEN].strip()
    if len(suffix) > _MAX_REMOTE_REGION_LEN:
        region = suffix[:_MAX_REMOTE_REGION_LEN].rstrip()
    return region

_COUNTRY_LOCATION = {
    "USA": "United States",
    "US": "United States",
    "CANADA": "Canada",
    "CA": "Canada",
    "UK": "United Kingdom",
    "GB": "United Kingdom",
}


@dataclass(frozen=True)
class ParsedLocation:
    """Scrape-ready location derived from a user-facing location string."""

    raw: str
    jobspy_location: str
    browser_location: str
    is_remote: bool
    country_indeed: str
    omit_hours_old: bool


def _default_country_location(country: str) -> str:
    key = country.strip().upper()
    return _COUNTRY_LOCATION.get(key, country.strip())


def parse_search_location(
    raw: str,
    *,
    default_country: str = "USA",
    remote_preferred: bool = False,
) -> ParsedLocation:
    """Map free-text locations to Indeed/JobSpy parameters."""
    text = raw.strip()
    if not text:
        raise ValueError("location must not be empty")

    normalized = re.sub(r"\s+", " ", text)
    if _REMOTE_US_RE.match(normalized) or (
        normalized.lower() == "remote" and default_country.upper() in {"USA", "US"}
    ):
        return ParsedLocation(
            raw=text,
            jobspy_location="United States",
            browser_location="United States",
            is_remote=True,
            country_indeed=default_country,
            omit_hours_old=True,
        )

    if _REMOTE_CA_RE.match(normalized):
        return ParsedLocation(
            raw=text,
            jobspy_location="Canada",
            browser_location="Canada",
            is_remote=True,
            country_indeed="Canada",
            omit_hours_old=True,
        )

    remote_region = _remote_generic_region(normalized)
    if remote_region is not None:
        region = remote_region.strip()
        if not region or region.lower() in {"usa", "us", "u.s.", "u.s.a.", "united states"}:
            return parse_search_location(
                "remote - usa",
                default_country=default_country,
                remote_preferred=remote_preferred,
            )
        if region.lower() in {"canada", "ca"}:
            return parse_search_location(
                "remote - canada",
                default_country=default_country,
                remote_preferred=remote_preferred,
            )
        # Unknown remote region — still enable remote filter, keep region as location hint.
        return ParsedLocation(
            raw=text,
            jobspy_location=region.title(),
            browser_location=region.title(),
            is_remote=True,
            country_indeed=default_country,
            omit_hours_old=True,
        )

    if remote_preferred and "remote" in normalized.lower():
        return parse_search_location(
            f"remote - {default_country}",
            default_country=default_country,
            remote_preferred=False,
        )

    return ParsedLocation(
        raw=text,
        jobspy_location=text,
        browser_location=text,
        is_remote=False,
        country_indeed=default_country,
        omit_hours_old=False,
    )


def dedupe_parsed_locations(parsed: list[ParsedLocation]) -> list[ParsedLocation]:
    """Drop duplicate scrape queries (e.g. ``remote`` and ``remote - usa``)."""
    seen: set[tuple[str, bool, str]] = set()
    ordered: list[ParsedLocation] = []
    for item in parsed:
        key = (item.jobspy_location.casefold(), item.is_remote, item.country_indeed.casefold())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def parse_locations_for_scrape(
    locations: list[str],
    *,
    default_country: str = "USA",
    remote_preferred: bool = False,
) -> list[ParsedLocation]:
    """Parse and dedupe all configured locations."""
    parsed = [
        parse_search_location(
            loc,
            default_country=default_country,
            remote_preferred=remote_preferred,
        )
        for loc in locations
        if loc.strip()
    ]
    return dedupe_parsed_locations(parsed)
