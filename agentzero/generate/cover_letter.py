"""Résumé-driven cover letter generation for the web job card."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentzero.models import JobPosting

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

COVER_LETTER_DIR = Path("output/cover_letters")
MAX_COVER_LETTER_CHARS = 32_768
MAX_RESUME_CHARS = 12_000

COVER_LETTER_JOB_FIELDS = frozenset(
    {"title", "company", "location", "remote", "description"},
)

COVER_LETTER_SYSTEM_PROMPT = (
    "You write cover letters for a job seeker preparing for interviews. "
    "Review the candidate's résumé history and experience and the target role's "
    "requirements. Make a fact-based, neutral-tone argument that this person would "
    "make a positive impact in the role. Ground every claim in specific experience "
    "from the résumé matched to specific requirements from the role. "
    "No truisms, no catch-phrases, no filler. "
    "Use adjectives sparingly — only when tied to a concrete fact. "
    "Write in first person as the candidate. "
    "Output plain text only (no markdown headers, no JSON). "
    "Length: about 250–400 words unless the role clearly warrants less."
)


def cover_letter_path(job_id: str, *, base_dir: Path = COVER_LETTER_DIR) -> Path:
    """Path to the on-disk cover letter for ``job_id``."""
    safe_id = job_id.replace("/", "_").replace("\\", "_")
    return base_dir / f"{safe_id}.txt"


def _truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + "… [truncated]"


def _job_payload_for_cover_letter(job: JobPosting, *, max_description_chars: int) -> dict:
    data = job.model_dump(mode="json", include=COVER_LETTER_JOB_FIELDS)
    description = data.get("description")
    if isinstance(description, str):
        data["description"] = _truncate(description, max_description_chars)
    return data


def _build_user_prompt(job: JobPosting, resume_text: str, *, max_description_chars: int) -> str:
    payload = {
        "resume_text": _truncate(resume_text.strip(), MAX_RESUME_CHARS),
        "job": _job_payload_for_cover_letter(job, max_description_chars=max_description_chars),
    }
    return json.dumps(payload, default=str)


def generate_cover_letter_text(
    job: JobPosting,
    resume_text: str,
    *,
    llm: LLMProvider,
    max_description_chars: int | None = None,
) -> str:
    """Call the LLM and return validated cover letter plain text."""
    if max_description_chars is None:
        from agentzero.config import get_settings

        max_description_chars = get_settings().rank_description_max_chars

    if not resume_text.strip():
        raise ValueError("resume text is empty")

    response = llm.complete(
        system=COVER_LETTER_SYSTEM_PROMPT,
        user=_build_user_prompt(job, resume_text, max_description_chars=max_description_chars),
    )
    text = response.strip()
    if not text:
        raise ValueError("LLM returned empty cover letter")
    if len(text) > MAX_COVER_LETTER_CHARS:
        raise ValueError(f"cover letter exceeds {MAX_COVER_LETTER_CHARS} characters")
    return text


def read_cover_letter(job_id: str, *, base_dir: Path = COVER_LETTER_DIR) -> str | None:
    path = cover_letter_path(job_id, base_dir=base_dir)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def save_cover_letter(
    job_id: str,
    text: str,
    *,
    base_dir: Path = COVER_LETTER_DIR,
) -> Path:
    """Persist operator-edited or generated cover letter text."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("cover letter text is empty")
    if len(cleaned) > MAX_COVER_LETTER_CHARS:
        raise ValueError(f"cover letter exceeds {MAX_COVER_LETTER_CHARS} characters")
    path = cover_letter_path(job_id, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cleaned, encoding="utf-8", newline="\n")
    return path


def generate_cover_letter(
    job: JobPosting,
    resume_text: str,
    *,
    llm: LLMProvider,
    base_dir: Path = COVER_LETTER_DIR,
    max_description_chars: int | None = None,
) -> Path:
    """Generate via LLM and write to ``output/cover_letters/{job_id}.txt``."""
    text = generate_cover_letter_text(
        job,
        resume_text,
        llm=llm,
        max_description_chars=max_description_chars,
    )
    return save_cover_letter(job.job_id, text, base_dir=base_dir)
