"""Remote-only scrape policy: query shaping and post-scrape listing filter."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from agentzero.models import JobPosting

if TYPE_CHECKING:
    from agentzero.config import Settings

REMOTE_USA_LOCATION = "remote - usa"

_ONSITE_LOCATION_RE = re.compile(
    r"\b(?:"
    r"on[-\s]?site|in[-\s]?office|in person|hybrid"
    r")\b",
    re.IGNORECASE,
)


def location_is_explicitly_non_remote(location: str | None) -> bool:
    """True when location text clearly indicates on-site or hybrid work."""
    if not location or not location.strip():
        return False
    return bool(_ONSITE_LOCATION_RE.search(location.strip()))


def trust_remote_search_listing(
    location: str | None,
    *,
    remote: bool | None,
    remote_search: bool,
) -> bool | None:
    """Trust remote-filtered board results unless location says hybrid/on-site."""
    if not remote_search:
        return remote
    if remote is True:
        return True
    if location_is_explicitly_non_remote(location):
        return False
    return True


def apply_remote_search_trust_to_record(record: dict, *, remote_search: bool) -> None:
    """Mutate a raw scrape record when the query used a remote board filter."""
    if not remote_search:
        return
    location = record.get("location")
    loc = str(location).strip() if location else None
    existing = record.get("remote")
    remote_bool = existing if isinstance(existing, bool) else None
    record["remote"] = trust_remote_search_listing(
        loc, remote=remote_bool, remote_search=True
    )


def format_remote_filter_skips(rejected: list[JobPosting], *, limit: int = 25) -> list[str]:
    """Human-readable lines for listings dropped by the remote filter."""
    lines: list[str] = []
    for job in rejected[:limit]:
        loc = job.location or "(no location)"
        lines.append(f"  - {job.title} @ {job.company} [{job.source}] loc={loc!r}")
    if len(rejected) > limit:
        lines.append(f"  ... and {len(rejected) - limit} more")
    return lines


def apply_remote_only_settings(settings: Settings) -> Settings:
    """Force remote-USA scrape targets when ``remote_only`` is enabled."""
    if not settings.remote_only:
        return settings
    return settings.model_copy(
        update={
            "locations": [REMOTE_USA_LOCATION],
            "remote_preferred": True,
        }
    )


def parse_locations_for_scrape_remote_aware(
    settings: Settings,
    *,
    default_country: str | None = None,
) -> list:
    """Parse locations; when ``remote_only``, drop non-remote query targets."""
    from agentzero.scrape.location import parse_locations_for_scrape

    country = default_country or settings.country_indeed
    parsed = parse_locations_for_scrape(
        settings.locations,
        default_country=country,
        remote_preferred=settings.remote_preferred,
    )
    remote_only = getattr(settings, "remote_only", True)
    if not remote_only:
        return parsed
    remote_only = [item for item in parsed if item.is_remote]
    if remote_only:
        return remote_only
    from agentzero.scrape.location import parse_search_location

    return [
        parse_search_location(
            REMOTE_USA_LOCATION,
            default_country=country,
            remote_preferred=True,
        )
    ]


_USA_REMOTE_LOCATION_RE = re.compile(
    r"^(?:united states|usa|u\.?s\.?a?\.?|us)$",
    re.IGNORECASE,
)
_STATE_ONLY_RE = re.compile(r"^[A-Z]{2}$")
_STATE_NAME_RE = re.compile(
    r"^(?:alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|"
    r"florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|"
    r"maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|"
    r"nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|"
    r"north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|"
    r"south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|"
    r"wisconsin|wyoming)$",
    re.IGNORECASE,
)


def job_is_remote(job: JobPosting) -> bool:
    """Return True when a listing is fully remote (not hybrid / on-site)."""
    from agentzero.apply.tracking import is_application_locked

    if is_application_locked(job):
        return True

    if job.remote is True:
        return True
    if job.remote is False:
        return False

    location = (job.location or "").strip()
    if not location:
        return False

    lowered = location.lower()
    if _ONSITE_LOCATION_RE.search(lowered):
        return False
    if "remote" in lowered or "work from home" in lowered or "wfh" in lowered:
        return True
    if _USA_REMOTE_LOCATION_RE.match(lowered):
        return True
    if _STATE_ONLY_RE.match(location.strip()):
        return True
    if _STATE_NAME_RE.match(lowered):
        return True
    # Anything else (incl. explicit "City, ST") is treated as non-remote.
    return False


def filter_remote_jobs(jobs: list[JobPosting]) -> tuple[list[JobPosting], list[JobPosting]]:
    """Split *jobs* into remote-eligible vs rejected (non-remote / on-site)."""
    kept: list[JobPosting] = []
    rejected: list[JobPosting] = []
    for job in jobs:
        if job_is_remote(job):
            kept.append(job)
        else:
            rejected.append(job)
    return kept, rejected
