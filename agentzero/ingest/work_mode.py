"""Work-mode selection (remote USA vs in-office) for search prompts and scrape targeting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agentzero.config import Settings
from agentzero.ingest.search_profile import ResumeSearchProfile, apply_search_profile
from agentzero.scrape.jobspy_params import build_jobspy_scrape_kwargs
from agentzero.scrape.location import parse_locations_for_scrape

WorkMode = Literal["remote", "in_office"]

REMOTE_USA_CANONICAL = "remote - usa"


@dataclass(frozen=True)
class WorkModeSelection:
    mode: WorkMode
    locations: list[str]
    remote_preferred: bool
    country_indeed: str


def parse_work_mode(raw: str, *, default: WorkMode = "remote") -> WorkMode:
    """Parse ``R``/``remote`` vs ``I``/``in-office`` (case-insensitive)."""
    text = raw.strip().lower()
    if not text:
        return default
    if text in {"r", "remote", "rem", "1", "wfh", "work from home"}:
        return "remote"
    if text in {"i", "in", "office", "in-office", "in office", "onsite", "on-site", "2"}:
        return "in_office"
    raise ValueError(
        "Work mode must be Remote (R) or In-office (I). "
        f"Got: {raw!r}"
    )


def infer_default_work_mode(profile: ResumeSearchProfile) -> WorkMode:
    """Guess default from résumé snapshot when user presses Enter."""
    if profile.remote_preferred:
        return "remote"
    parsed = parse_locations_for_scrape(
        profile.locations,
        default_country=profile.country_indeed or "USA",
        remote_preferred=False,
    )
    if parsed and all(item.is_remote for item in parsed):
        return "remote"
    return "in_office"


def selection_from_work_mode(
    mode: WorkMode,
    *,
    office_locations: list[str] | None = None,
    country_indeed: str = "USA",
) -> WorkModeSelection:
    """Build profile/scrape fields from a work-mode choice."""
    if mode == "remote":
        return WorkModeSelection(
            mode="remote",
            locations=[REMOTE_USA_CANONICAL],
            remote_preferred=True,
            country_indeed=country_indeed,
        )

    cities = [loc.strip() for loc in office_locations or [] if loc.strip()]
    if not cities:
        raise ValueError("In-office mode requires at least one city or region")
    return WorkModeSelection(
        mode="in_office",
        locations=cities,
        remote_preferred=False,
        country_indeed=country_indeed,
    )


def apply_work_mode_selection(
    profile: ResumeSearchProfile,
    selection: WorkModeSelection,
) -> ResumeSearchProfile:
    """Merge work-mode choice into a search profile snapshot."""
    return profile.model_copy(
        update={
            "locations": selection.locations,
            "remote_preferred": selection.remote_preferred,
            "country_indeed": selection.country_indeed,
        }
    )


def format_work_mode_summary(selection: WorkModeSelection) -> str:
    if selection.mode == "remote":
        return "Work mode: Remote (USA) - searches United States with remote filter"
    return f"Work mode: In-office - {', '.join(selection.locations)}"


def trace_scrape_targets(
    settings: Settings,
    *,
    sample_term: str | None = None,
) -> list[dict[str, object]]:
    """Show how settings map to JobSpy kwargs (one row per term × location)."""
    term = sample_term or (settings.search_terms[0] if settings.search_terms else "engineer")
    rows: list[dict[str, object]] = []
    for parsed in parse_locations_for_scrape(
        settings.locations,
        default_country=settings.country_indeed,
        remote_preferred=settings.remote_preferred,
    ):
        kwargs = build_jobspy_scrape_kwargs(
            settings,
            site="indeed",
            term=term,
            parsed=parsed,
        )
        rows.append(
            {
                "profile_location": parsed.raw,
                "jobspy_location": kwargs["location"],
                "is_remote": kwargs.get("is_remote", False),
                "hours_old": kwargs.get("hours_old"),
                "country_indeed": kwargs["country_indeed"],
            }
        )
    return rows


def preview_work_mode_flow(
    profile: ResumeSearchProfile,
    selection: WorkModeSelection,
    base_settings: Settings,
    *,
    sample_term: str | None = None,
) -> dict[str, object]:
    """End-to-end trace: work mode → profile → settings → scrape kwargs."""
    updated_profile = apply_work_mode_selection(profile, selection)
    effective = apply_search_profile(base_settings, updated_profile)
    return {
        "work_mode": selection.mode,
        "profile_locations": updated_profile.locations,
        "profile_remote_preferred": updated_profile.remote_preferred,
        "profile_country_indeed": updated_profile.country_indeed,
        "scrape_targets": trace_scrape_targets(effective, sample_term=sample_term),
    }
