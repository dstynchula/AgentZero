"""Résumé-linked search terms — extracted fresh from the résumé on every run."""

from __future__ import annotations

import hashlib
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
    salary_max: float | None = None
    source_resume_path: str
    source_fingerprint: str
    updated_at: str


# Avoid duplicate LLM calls when ingest + scrape run in the same process.
_session_profile: ResumeSearchProfile | None = None


def clear_search_profile_session_cache() -> None:
    """Clear the in-process search-profile cache (for tests)."""
    global _session_profile
    _session_profile = None


def search_profile_storage_dir(*, settings: Settings | None = None) -> Path:
    """Writable directory for the snapshot (beside SQLite; safe in Docker)."""
    if settings is None:
        from agentzero.config import get_settings

        settings = get_settings()
    return settings.db_path.parent


def legacy_search_profile_path(resume_dir: Path = RESUME_DIR) -> Path:
    """Pre-P33 path kept for one-time fallback reads."""
    return resume_dir / SEARCH_PROFILE_FILENAME


def search_profile_path(
    resume_dir: Path = RESUME_DIR,
    *,
    settings: Settings | None = None,
) -> Path:
    """Canonical snapshot path under ``data/`` (not ``resume/``)."""
    _ = resume_dir  # résumé files stay under resume_dir; snapshot is separate
    return search_profile_storage_dir(settings=settings) / SEARCH_PROFILE_FILENAME


def resume_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_search_profile(
    resume_dir: Path = RESUME_DIR,
    *,
    settings: Settings | None = None,
) -> ResumeSearchProfile | None:
    """Read snapshot from ``data/search_profile.json``, else legacy ``resume/`` path."""
    for path in (
        search_profile_path(resume_dir, settings=settings),
        legacy_search_profile_path(resume_dir),
    ):
        if path.is_file():
            return ResumeSearchProfile.model_validate_json(path.read_text(encoding="utf-8"))
    return None


def load_matching_search_profile(
    resume_dir: Path = RESUME_DIR,
    *,
    settings: Settings | None = None,
) -> ResumeSearchProfile | None:
    """Return the on-disk snapshot when it matches the latest résumé file."""
    try:
        resume_path = find_latest_resume(resume_dir)
    except FileNotFoundError:
        return None
    snapshot = load_search_profile(resume_dir, settings=settings)
    if snapshot is None:
        return None
    if snapshot.source_fingerprint != resume_fingerprint(resume_path):
        return None
    return snapshot


def save_search_profile(
    profile: ResumeSearchProfile,
    resume_dir: Path = RESUME_DIR,
    *,
    settings: Settings | None = None,
) -> Path:
    path = search_profile_path(resume_dir, settings=settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _parse_json_object(text: str) -> dict:
    from agentzero.llm.json_util import parse_llm_json_object

    return parse_llm_json_object(text)


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
            "salary_min (number USD annual — minimum the candidate would accept; optional). "
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
        salary_max=None,
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
    force_refresh: bool = False,
    prefer_snapshot: bool = True,
) -> ResumeSearchProfile:
    """Read the latest résumé and extract search terms via the LLM.

    Reuses the in-process result when the résumé file is unchanged. When
    ``prefer_snapshot`` is true, also reuses ``data/search_profile.json`` if
    its fingerprint matches (fast path before the interactive prompt).
    """
    global _session_profile

    path = resume_path or find_latest_resume(resume_dir)
    fingerprint = resume_fingerprint(path)
    if (
        not force_refresh
        and _session_profile is not None
        and _session_profile.source_fingerprint == fingerprint
    ):
        return _session_profile

    if not force_refresh and prefer_snapshot:
        snapshot = load_matching_search_profile(resume_dir)
        if snapshot is not None:
            _session_profile = snapshot
            return snapshot

    text = raw_text if raw_text is not None else read_resume_text(path)
    profile = extract_search_profile(text, resume_path=path, llm=llm)
    if save_snapshot:
        save_search_profile(profile, resume_dir)
    _session_profile = profile
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
    if profile.remote_preferred is not None:
        updates["remote_preferred"] = profile.remote_preferred
    if profile.salary_min is not None:
        updates["salary_min"] = profile.salary_min
    return settings.model_copy(update=updates)


def get_effective_settings(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
    resume_dir: Path = RESUME_DIR,
) -> Settings:
    """Merge env settings with search terms extracted from the latest résumé.

    When ``llm`` is provided, search terms are re-derived from the résumé on the
    first call in this process (cached when the résumé file is unchanged). Without
    ``llm``, falls back to env/.env only.
    """
    from agentzero.config import get_settings
    from agentzero.scrape.remote_policy import apply_remote_only_settings

    base = settings or get_settings()
    if llm is None or not resume_dir.is_dir():
        return apply_remote_only_settings(base)
    try:
        profile = resolve_search_from_resume(llm=llm, resume_dir=resume_dir)
    except FileNotFoundError:
        return apply_remote_only_settings(base)
    if profile is None:
        return apply_remote_only_settings(base)
    return apply_remote_only_settings(apply_search_profile(base, profile))
