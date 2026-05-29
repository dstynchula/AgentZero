"""Ingest résumé files from ``resume/`` into a structured profile."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

RESUME_DIR = Path("resume")
SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}


class ExperienceEntry(BaseModel):
    """One role on the résumé, ordered newest-first in ``ResumeProfile.experience``."""

    title: str
    company: str | None = None
    start: str | None = None
    end: str | None = None
    is_current: bool = False


def find_latest_resume(resume_dir: Path = RESUME_DIR) -> Path:
    candidates = sorted(
        (p for p in resume_dir.iterdir() if p.suffix.lower() in SUPPORTED_SUFFIXES),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No résumé found in {resume_dir}")
    return candidates[0]


class ResumeProfile(BaseModel):
    """Structured candidate profile extracted from a résumé."""

    name: str | None = None
    email: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    summary: str | None = None
    raw_text: str
    source_path: str

    @field_validator("experience", mode="before")
    @classmethod
    def _coerce_experience(cls, value: object) -> object:
        if not value:
            return []
        if not isinstance(value, list):
            return value
        out: list[object] = []
        for item in value:
            if isinstance(item, str):
                out.append({"title": item})
            else:
                out.append(item)
        return out


def read_resume_text(path: Path) -> str:
    """Read plain text from supported résumé formats."""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError(
                "PDF résumés require pypdf. Install with: pip install pypdf"
            ) from exc
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        try:
            import docx
        except ImportError as exc:
            raise ImportError(
                "DOCX résumés require python-docx. Install with: pip install python-docx"
            ) from exc
        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)
    raise ValueError(f"Unsupported résumé format: {suffix}")


def _parse_profile_json(text: str) -> dict:
    import json

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise TypeError("LLM response must be a JSON object")
    return data


def extract_resume_profile(raw_text: str, *, llm: LLMProvider) -> ResumeProfile:
    """Use the LLM to extract structured fields from résumé plain text."""
    response = llm.complete(
        system=(
            "Extract résumé data as JSON with keys: name, email, skills (array), "
            "experience (array of objects, NEWEST role first, each with: title, company, "
            "start, end, is_current boolean), summary. Return JSON only."
        ),
        user=raw_text,
    )
    data = _parse_profile_json(response)
    return ResumeProfile(
        name=data.get("name"),
        email=data.get("email"),
        skills=list(data.get("skills") or []),
        experience=data.get("experience") or [],
        summary=data.get("summary"),
        raw_text=raw_text,
        source_path="",
    )


def ingest_resume(
    path: Path | None = None,
    *,
    llm: LLMProvider,
    resume_dir: Path = RESUME_DIR,
    refresh_search: bool = True,
) -> ResumeProfile:
    """Load the newest résumé in ``resume_dir`` (or an explicit path) and parse it."""
    if path is None:
        path = find_latest_resume(resume_dir)

    raw_text = read_resume_text(path)
    profile = extract_resume_profile(raw_text, llm=llm)
    profile = profile.model_copy(update={"source_path": str(path)})

    if refresh_search:
        from agentzero.ingest.search_profile import resolve_search_from_resume

        resolve_search_from_resume(
            llm=llm,
            resume_dir=resume_dir,
            resume_path=path,
            raw_text=raw_text,
        )

    return profile
