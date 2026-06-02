"""Search title selection for the web settings UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentzero.config import Settings
from agentzero.web.operator_config import OperatorScrapeConfig

if TYPE_CHECKING:
    from agentzero.ingest.search_profile import ResumeSearchProfile


@dataclass(frozen=True, slots=True)
class TitleRow:
    term: str
    selected: bool


def all_display_terms(
    profile_terms: list[str],
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    """Titles shown in Settings; operator list is authoritative once configured."""
    if operator is None:
        return list(profile_terms)
    return list(operator.search_terms)


def effective_search_terms(
    profile_terms: list[str],
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    """Titles used for scrape; operator list is authoritative once configured."""
    if operator is None:
        return list(profile_terms)
    return list(operator.search_terms)


def title_rows(
    profile_terms: list[str],
    operator: OperatorScrapeConfig | None,
) -> list[TitleRow]:
    active = {t.strip().lower() for t in effective_search_terms(profile_terms, operator)}
    return [
        TitleRow(term=term, selected=term.strip().lower() in active)
        for term in all_display_terms(profile_terms, operator)
    ]


def merge_title_selection(
    selected_profile: list[str],
    profile_terms: list[str],
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    """Checkbox save: keep operator order; update selection for profile rows shown."""
    if operator is None or not operator.search_terms:
        return normalize_title_selection(selected_profile, profile_terms)
    profile_lower = {t.strip().lower() for t in profile_terms}
    selected_lower = {t.strip().lower() for t in selected_profile}
    out: list[str] = []
    seen: set[str] = set()
    for term in operator.search_terms:
        key = term.strip().lower()
        if key in profile_lower:
            if key in selected_lower and key not in seen:
                out.append(term)
                seen.add(key)
        elif key not in seen:
            out.append(term)
            seen.add(key)
    for raw in selected_profile:
        key = raw.strip().lower()
        if key in profile_lower and key not in seen:
            allowed = {t.strip().lower(): t for t in profile_terms}
            out.append(allowed[key])
            seen.add(key)
    return out


def add_operator_title(
    config_path: Path,
    term: str,
    *,
    profile_terms: list[str],
) -> list[str]:
    from agentzero.web.operator_config import load_operator_config, patch_operator_config

    cleaned = term.strip()
    if not cleaned:
        raise ValueError("Title cannot be empty")
    existing = load_operator_config(config_path)
    active = effective_search_terms(profile_terms, existing)
    if cleaned.lower() in {t.strip().lower() for t in active}:
        return active
    updated = [*active, cleaned]
    patch_operator_config(config_path, search_terms=updated)
    return updated


def remove_operator_title(
    config_path: Path,
    term: str,
    *,
    profile_terms: list[str],
) -> list[str]:
    from agentzero.web.operator_config import load_operator_config, patch_operator_config

    key = term.strip().lower()
    if not key:
        raise ValueError("Title cannot be empty")
    existing = load_operator_config(config_path)
    active = effective_search_terms(profile_terms, existing)
    updated = [t for t in active if t.strip().lower() != key]
    patch_operator_config(config_path, search_terms=updated)
    return updated


def normalize_title_selection(
    selected: list[str],
    profile_terms: list[str],
) -> list[str]:
    """Keep résumé profile order; ignore unknown titles."""
    if not profile_terms:
        return []
    allowed = {t.strip().lower(): t for t in profile_terms}
    out: list[str] = []
    seen: set[str] = set()
    for raw in selected:
        key = raw.strip().lower()
        if key in allowed and key not in seen:
            out.append(allowed[key])
            seen.add(key)
    return out


def apply_operator_search_terms(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> Settings:
    if operator is None or not operator.search_terms:
        return settings
    terms = list(operator.search_terms)
    if not terms:
        return settings
    return settings.model_copy(
        update={
            "search_terms": terms,
            "scrape_primary_query_only": len(terms) <= 1,
        }
    )


def search_profile_summary(profile: ResumeSearchProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "terms": list(profile.search_terms),
        "locations": list(profile.locations),
        "salary_min": profile.salary_min,
    }
