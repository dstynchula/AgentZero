"""Résumé-linked search terms — extracted fresh from the résumé on every run."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from agentzero.config import Settings
from agentzero.ingest.resume import (
    RESUME_DIR,
    ExperienceEntry,
    find_latest_resume,
    read_resume_text,
)

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

SEARCH_PROFILE_FILENAME = "search_profile.json"


class ResumeSearchProfile(BaseModel):
    """Job-search terms inferred from the résumé (also saved as a local snapshot)."""

    search_terms: list[str] = Field(min_length=1)
    locations: list[str] = Field(min_length=1)
    recent_roles: list[ExperienceEntry] = Field(default_factory=list)
    results_wanted: int | None = None
    hours_old: int | None = None
    country_indeed: str | None = None
    remote_preferred: bool | None = None
    salary_min: float | None = None
    source_resume_path: str
    source_fingerprint: str
    updated_at: str


def search_profile_path(resume_dir: Path = RESUME_DIR) -> Path:
    return resume_dir / SEARCH_PROFILE_FILENAME


def resume_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_search_profile(resume_dir: Path = RESUME_DIR) -> ResumeSearchProfile | None:
    """Read the last saved snapshot (for inspection only — not used to drive searches)."""
    path = search_profile_path(resume_dir)
    if not path.is_file():
        return None
    return ResumeSearchProfile.model_validate_json(path.read_text(encoding="utf-8"))


def save_search_profile(profile: ResumeSearchProfile, resume_dir: Path = RESUME_DIR) -> Path:
    path = search_profile_path(resume_dir)
    path.write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise TypeError("LLM response must be a JSON object")
    return data


def prioritize_search_terms(
    recent_roles: list[ExperienceEntry],
    llm_terms: list[str],
    *,
    max_terms: int = 6,
) -> list[str]:
    """Put titles from the most recent roles first, then remaining LLM suggestions."""
    ordered: list[str] = []
    seen: set[str] = set()

    for role in recent_roles:
        title = role.title.strip()
        key = title.lower()
        if title and key not in seen:
            ordered.append(title)
            seen.add(key)

    for term in llm_terms:
        cleaned = term.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            ordered.append(cleaned)
            seen.add(key)
        if len(ordered) >= max_terms:
            break

    return ordered[:max_terms] or llm_terms[:max_terms]


def extract_search_profile(
    raw_text: str,
    *,
    resume_path: Path,
    llm: LLMProvider,
) -> ResumeSearchProfile:
    """Use the LLM to infer search terms and locations from résumé text."""
    response = llm.complete(
        system=(
            "From this résumé, infer job-search parameters. Return JSON only with keys: "
            "recent_roles (array of objects, NEWEST job first, each with title, company, "
            "start, end, is_current), "
            "search_terms (array of 3-6 additional job titles/keywords), "
            "locations (array of cities/regions or Remote), "
            "remote_preferred (boolean, optional), "
            "salary_min (number USD annual, optional). "
            "Base search_terms on the candidate's most recent roles; "
            "older roles are lower priority."
        ),
        user=raw_text,
    )
    data = _parse_json_object(response)
    recent_roles = [
        ExperienceEntry.model_validate(role) for role in data.get("recent_roles") or []
    ]
    llm_terms = [str(t).strip() for t in data.get("search_terms") or [] if str(t).strip()]
    terms = prioritize_search_terms(recent_roles, llm_terms)
    locations = [str(loc).strip() for loc in data.get("locations") or [] if str(loc).strip()]
    if not terms:
        raise ValueError("LLM returned no search_terms")
    if not locations:
        locations = ["Remote"]
    return ResumeSearchProfile(
        search_terms=terms,
        locations=locations,
        recent_roles=recent_roles,
        remote_preferred=data.get("remote_preferred"),
        salary_min=float(data["salary_min"]) if data.get("salary_min") is not None else None,
        source_resume_path=str(resume_path),
        source_fingerprint=resume_fingerprint(resume_path),
        updated_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )


def resolve_search_from_resume(
    *,
    llm: LLMProvider,
    resume_dir: Path = RESUME_DIR,
    resume_path: Path | None = None,
    raw_text: str | None = None,
    save_snapshot: bool = True,
) -> ResumeSearchProfile:
    """Always read the latest résumé and extract search terms (no cache reads)."""
    path = resume_path or find_latest_resume(resume_dir)
    text = raw_text if raw_text is not None else read_resume_text(path)
    profile = extract_search_profile(text, resume_path=path, llm=llm)
    if save_snapshot:
        save_search_profile(profile, resume_dir)
    return profile


def apply_search_profile(settings: Settings, profile: ResumeSearchProfile | None) -> Settings:
    if profile is None:
        return settings
    updates: dict = {
        "search_terms": profile.search_terms,
        "locations": profile.locations,
    }
    if profile.results_wanted is not None:
        updates["results_wanted"] = profile.results_wanted
    if profile.hours_old is not None:
        updates["hours_old"] = profile.hours_old
    if profile.country_indeed is not None:
        updates["country_indeed"] = profile.country_indeed
    return settings.model_copy(update=updates)


def get_effective_settings(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
    resume_dir: Path = RESUME_DIR,
) -> Settings:
    """Merge env settings with search terms extracted from the latest résumé.

    When ``llm`` is provided, search terms are **always** re-derived from the résumé
    on this call (each pipeline/scrape run). Without ``llm``, falls back to env/.env only.
    """
    from agentzero.config import get_settings

    base = settings or get_settings()
    if llm is None or not resume_dir.is_dir():
        return base
    try:
        profile = resolve_search_from_resume(llm=llm, resume_dir=resume_dir)
    except FileNotFoundError:
        return base
    return apply_search_profile(base, profile)
