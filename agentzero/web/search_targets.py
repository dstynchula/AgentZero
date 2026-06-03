"""Validated operator search targets (location, comp, remote) for the web Scraper UI."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentzero.config import Settings
from agentzero.ingest.work_mode import (
    WorkMode,
    infer_default_work_mode,
    selection_from_work_mode,
)
from agentzero.scrape.location import parse_search_location

if TYPE_CHECKING:
    from agentzero.ingest.search_profile import ResumeSearchProfile
    from agentzero.web.operator_config import OperatorScrapeConfig

MAX_LOCATION_LEN = 120
MAX_LOCATIONS = 5
MAX_LOCATIONS_PAYLOAD = 10_240
MAX_SALARY_MIN = 10_000_000.0
MAX_TITLE_LEN = 200

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_FORM_WORK_MODES = frozenset({"remote", "in_office"})


@dataclass(frozen=True, slots=True)
class ParsedSearchTargets:
    work_mode: WorkMode
    locations: list[str]
    salary_min: float | None
    scrape_remote_only: bool


def sanitize_free_text(value: str, *, max_len: int, field_name: str) -> str:
    """Strip hostile content from a single-line user string."""
    if len(value) > max_len * 4:
        raise ValueError(f"{field_name} is too long")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    if _CONTROL_CHAR_RE.search(cleaned):
        raise ValueError(f"{field_name} contains invalid characters")
    if len(cleaned) > max_len:
        raise ValueError(f"{field_name} must be at most {max_len} characters")
    return cleaned


def sanitize_optional_free_text(value: str, *, max_len: int, field_name: str) -> str:
    """Like sanitize_free_text but allows empty after strip."""
    if len(value) > max_len * 4:
        raise ValueError(f"{field_name} is too long")
    cleaned = value.strip()
    if _CONTROL_CHAR_RE.search(cleaned):
        raise ValueError(f"{field_name} contains invalid characters")
    if len(cleaned) > max_len:
        raise ValueError(f"{field_name} must be at most {max_len} characters")
    return cleaned


def _split_csv_locations(text: str) -> list[str]:
    if len(text) > MAX_LOCATIONS_PAYLOAD:
        raise ValueError("Locations text is too long")
    sep = ";" if ";" in text else ","
    parts = [item.strip() for item in text.split(sep) if item.strip()]
    if len(parts) > MAX_LOCATIONS:
        raise ValueError(f"At most {MAX_LOCATIONS} locations allowed")
    return parts


def _validate_location_item(raw: str) -> str:
    cleaned = sanitize_free_text(raw, max_len=MAX_LOCATION_LEN, field_name="Location")
    if re.search(r"[<>]", cleaned):
        raise ValueError("Location contains invalid characters")
    try:
        parse_search_location(cleaned)
    except ValueError as exc:
        raise ValueError(f"Invalid location: {cleaned!r}") from exc
    return cleaned


def parse_salary_min_field(text: str) -> float | None:
    """Parse comp floor from form text; empty clears the floor."""
    cleaned = text.strip().replace(",", "").replace("$", "")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError as exc:
        raise ValueError("Comp floor must be a number") from exc
    if not math.isfinite(value):
        raise ValueError("Comp floor must be a finite number")
    if value < 0:
        raise ValueError("Comp floor must be non-negative")
    if value > MAX_SALARY_MIN:
        raise ValueError(f"Comp floor must be at most ${MAX_SALARY_MIN:,.0f}")
    return value


def parse_work_mode_field(raw: str) -> WorkMode:
    text = raw.strip().lower()
    if text not in _FORM_WORK_MODES:
        raise ValueError("Work mode must be Remote or In-office")
    return "remote" if text == "remote" else "in_office"


def parse_search_targets_form(
    *,
    work_mode: str,
    locations_text: str,
    salary_min_text: str,
    scrape_remote_only: bool,
    country_indeed: str = "USA",
) -> ParsedSearchTargets:
    """Validate POST fields from the Scraper search-targets form."""
    mode = parse_work_mode_field(work_mode)
    salary_min = parse_salary_min_field(salary_min_text)

    if mode == "remote":
        selection = selection_from_work_mode("remote", country_indeed=country_indeed)
        locations = list(selection.locations)
    else:
        parts = _split_csv_locations(locations_text)
        if not parts:
            raise ValueError("In-office mode requires at least one location")
        locations = [_validate_location_item(part) for part in parts]
        selection = selection_from_work_mode(
            "in_office",
            office_locations=locations,
            country_indeed=country_indeed,
        )
        locations = list(selection.locations)

    return ParsedSearchTargets(
        work_mode=mode,
        locations=locations,
        salary_min=salary_min,
        scrape_remote_only=bool(scrape_remote_only),
    )


def search_targets_configured(operator: OperatorScrapeConfig | None) -> bool:
    return operator is not None and operator.search_targets_configured


def _profile_work_mode(profile: ResumeSearchProfile) -> WorkMode:
    return infer_default_work_mode(profile)


def effective_search_targets_form(
    profile: ResumeSearchProfile | None,
    operator: OperatorScrapeConfig | None,
    *,
    settings: Settings,
) -> dict[str, object]:
    """Values for the Search targets form (operator overrides when configured)."""
    if profile is None:
        return {
            "configured": search_targets_configured(operator),
            "work_mode": "remote",
            "locations_text": "",
            "salary_min": "",
            "scrape_remote_only": settings.remote_only,
            "profile_hint": None,
        }

    profile_mode = _profile_work_mode(profile)
    profile_locations = ", ".join(
        loc for loc in profile.locations if "remote" not in loc.lower()
    )
    if profile_mode == "remote":
        profile_locations = "remote - usa"

    if search_targets_configured(operator):
        assert operator is not None
        mode = operator.work_mode or "remote"
        if mode == "remote":
            loc_text = ""
        else:
            loc_text = ", ".join(operator.locations)
        salary = operator.salary_min
        remote_only = operator.scrape_remote_only
    else:
        mode = profile_mode
        loc_text = profile_locations if profile_mode == "in_office" else ""
        salary = profile.salary_min
        remote_only = settings.remote_only

    salary_display = ""
    if salary is not None:
        salary_display = str(int(salary)) if salary == int(salary) else str(salary)

    profile_hint_parts: list[str] = []
    if profile.remote_preferred or profile_mode == "remote":
        profile_hint_parts.append("Remote (USA)")
    elif profile.locations:
        profile_hint_parts.append(", ".join(profile.locations))
    if profile.salary_min is not None:
        profile_hint_parts.append(f"comp floor ${profile.salary_min:,.0f}")

    return {
        "configured": search_targets_configured(operator),
        "work_mode": mode,
        "locations_text": loc_text,
        "salary_min": salary_display,
        "scrape_remote_only": remote_only,
        "profile_hint": "; ".join(profile_hint_parts) if profile_hint_parts else None,
    }


def apply_operator_search_targets(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> Settings:
    """Overlay saved operator location/comp/remote onto scrape settings."""
    if not search_targets_configured(operator):
        return settings
    assert operator is not None
    mode = operator.work_mode or "remote"
    if mode == "remote":
        selection = selection_from_work_mode("remote", country_indeed=settings.country_indeed)
    else:
        selection = selection_from_work_mode(
            "in_office",
            office_locations=list(operator.locations),
            country_indeed=settings.country_indeed,
        )
    return settings.model_copy(
        update={
            "locations": list(selection.locations),
            "remote_preferred": selection.remote_preferred,
            "country_indeed": selection.country_indeed,
            "salary_min": operator.salary_min,
            "remote_only": operator.scrape_remote_only,
        }
    )


def operator_search_targets_patch(parsed: ParsedSearchTargets) -> dict[str, object]:
    """Fields for patch_operator_config after a successful save."""
    return {
        "work_mode": parsed.work_mode,
        "locations": list(parsed.locations),
        "salary_min": parsed.salary_min,
        "scrape_remote_only": parsed.scrape_remote_only,
        "search_targets_configured": True,
    }
