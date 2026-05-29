"""Voice-matched cover letter drafts."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentzero.ingest.resume import ResumeProfile
from agentzero.ingest.voice import VoiceProfile
from agentzero.models import JobPosting

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

OUTPUT_DIR = Path("output/cover_letters")


def cover_letter_path(job: JobPosting) -> Path:
    safe_company = "".join(c if c.isalnum() else "_" for c in job.company)[:40]
    return OUTPUT_DIR / f"{job.job_id}_{safe_company}.md"


def generate_cover_letter(
    job: JobPosting,
    profile: ResumeProfile,
    voice: VoiceProfile,
    *,
    llm: LLMProvider,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """Draft a cover letter and write it to ``output_dir`` (idempotent path per job)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / cover_letter_path(job).name
    prompt = (
        f"Job: {job.title} at {job.company}\n"
        f"URL: {job.url}\n\n"
        f"Candidate summary: {profile.summary or profile.raw_text[:500]}\n\n"
        f"Voice style guide:\n{voice.style_guide}\n\n"
        f"Sample phrases: {', '.join(voice.sample_phrases)}\n"
    )
    body = llm.complete(
        system=(
            "Write a tailored cover letter in the candidate's voice. "
            "Use markdown. Do not invent false experience."
        ),
        user=prompt,
    )
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return path
