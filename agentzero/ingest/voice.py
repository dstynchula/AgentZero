"""Ingest writing samples from ``coverletters/`` to capture the candidate's voice."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

COVERLETTER_DIR = Path("coverletters")
SAMPLE_SUFFIXES = {".txt", ".md"}


class VoiceProfile(BaseModel):
    """Style guide derived from past cover letters / writing samples."""

    tone: str | None = None
    sample_phrases: list[str] = Field(default_factory=list)
    style_guide: str
    source_files: list[str] = Field(default_factory=list)


def load_writing_samples(directory: Path = COVERLETTER_DIR) -> tuple[str, list[str]]:
    """Concatenate text samples from ``directory``."""
    paths = sorted(
        p for p in directory.iterdir() if p.suffix.lower() in SAMPLE_SUFFIXES
    )
    if not paths:
        raise FileNotFoundError(f"No writing samples found in {directory}")
    parts = [p.read_text(encoding="utf-8") for p in paths]
    return "\n\n---\n\n".join(parts), [str(p) for p in paths]


def _parse_voice_json(text: str) -> dict:
    import json

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise TypeError("LLM response must be a JSON object")
    return data


def extract_voice_profile(combined_text: str, *, llm: LLMProvider) -> VoiceProfile:
    """Use the LLM to summarize writing style from samples."""
    response = llm.complete(
        system=(
            "Analyze writing samples and return JSON with: tone (string), "
            "sample_phrases (array of short representative phrases), "
            "style_guide (paragraph describing voice for cover letters). JSON only."
        ),
        user=combined_text,
    )
    data = _parse_voice_json(response)
    return VoiceProfile(
        tone=data.get("tone"),
        sample_phrases=list(data.get("sample_phrases") or []),
        style_guide=str(data.get("style_guide") or ""),
    )


def ingest_voice_samples(
    *,
    llm: LLMProvider,
    directory: Path = COVERLETTER_DIR,
) -> VoiceProfile:
    """Load all writing samples and build a voice profile."""
    combined, sources = load_writing_samples(directory)
    profile = extract_voice_profile(combined, llm=llm)
    return profile.model_copy(update={"source_files": sources})
