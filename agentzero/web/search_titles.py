"""Search title selection for the web settings UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentzero.config import Settings
from agentzero.web.operator_config import OperatorScrapeConfig

if TYPE_CHECKING:
    from agentzero.ingest.search_profile import ResumeSearchProfile


@dataclass(frozen=True, slots=True)
class TitleRow:
    term: str
    selected: bool


def effective_search_terms(
    profile_terms: list[str],
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    """Titles used for scrape: operator subset, or full profile when unset."""
    if not profile_terms:
        return []
    if operator is None or not operator.search_terms:
        return list(profile_terms)
    allowed = {t.strip().lower() for t in operator.search_terms}
    selected = [t for t in profile_terms if t.strip().lower() in allowed]
    return selected or list(profile_terms)


def title_rows(
    profile_terms: list[str],
    operator: OperatorScrapeConfig | None,
) -> list[TitleRow]:
    active = {t.strip().lower() for t in effective_search_terms(profile_terms, operator)}
    return [
        TitleRow(term=term, selected=term.strip().lower() in active)
        for term in profile_terms
    ]


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
    terms = normalize_title_selection(operator.search_terms, list(settings.search_terms))
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
