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


def _excluded_lower(operator: OperatorScrapeConfig | None) -> set[str]:
    if operator is None:
        return set()
    return {t.strip().lower() for t in operator.excluded_search_terms}


def all_display_terms(
    profile_terms: list[str],
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    """Résumé titles (minus removed) plus custom operator-only titles."""
    if operator is None:
        return list(profile_terms)
    excluded = _excluded_lower(operator)
    profile_lower = {t.strip().lower() for t in profile_terms}
    shown = [t for t in profile_terms if t.strip().lower() not in excluded]
    custom = [
        t
        for t in operator.search_terms
        if t.strip().lower() not in profile_lower and t.strip().lower() not in excluded
    ]
    return shown + custom


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


def sync_operator_titles_after_resume_load(
    config_path: Path,
    profile_terms: list[str],
) -> list[str]:
    """Merge new résumé titles into operator config; keep custom titles and removals."""
    from agentzero.web.operator_config import load_operator_config, patch_operator_config

    existing = load_operator_config(config_path) or OperatorScrapeConfig()
    if not existing.search_terms:
        patch_operator_config(config_path, search_terms=list(profile_terms))
        return list(profile_terms)

    excluded = _excluded_lower(existing)
    profile_lower = {t.strip().lower() for t in profile_terms}
    active: list[str] = []
    seen: set[str] = set()
    for term in existing.search_terms:
        key = term.strip().lower()
        if key in excluded:
            continue
        if key not in profile_lower:
            active.append(term)
            seen.add(key)
        elif key in profile_lower:
            active.append(term)
            seen.add(key)
    for term in profile_terms:
        key = term.strip().lower()
        if key in excluded or key in seen:
            continue
        active.append(term)
        seen.add(key)
    patch_operator_config(config_path, search_terms=active)
    return active


def merge_title_selection(
    selected_profile: list[str],
    profile_terms: list[str],
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    """Checkbox save: selected profile rows plus custom titles still in the list."""
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
    from agentzero.web.search_targets import MAX_TITLE_LEN, sanitize_free_text

    try:
        cleaned = sanitize_free_text(term, max_len=MAX_TITLE_LEN, field_name="Title")
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    existing = load_operator_config(config_path) or OperatorScrapeConfig()
    active = effective_search_terms(profile_terms, existing)
    key = cleaned.lower()
    excluded = [t for t in existing.excluded_search_terms if t.strip().lower() != key]
    if key in {t.strip().lower() for t in active}:
        patch_operator_config(
            config_path,
            search_terms=active,
            excluded_search_terms=excluded,
        )
        return active
    updated = [*active, cleaned]
    patch_operator_config(
        config_path,
        search_terms=updated,
        excluded_search_terms=excluded,
    )
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
    existing = load_operator_config(config_path) or OperatorScrapeConfig()
    active = effective_search_terms(profile_terms, existing)
    updated = [t for t in active if t.strip().lower() != key]
    profile_lower = {t.strip().lower() for t in profile_terms}
    excluded = list(existing.excluded_search_terms)
    excluded_keys = {t.strip().lower() for t in excluded}
    if key in profile_lower and key not in excluded_keys:
        excluded.append(next(t for t in profile_terms if t.strip().lower() == key))
    patch_operator_config(
        config_path,
        search_terms=updated,
        excluded_search_terms=excluded,
    )
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
