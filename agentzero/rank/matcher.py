"""LLM-based job vs résumé matching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentzero.ingest.resume import ResumeProfile
from agentzero.models import JobPosting

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider


@dataclass(frozen=True, slots=True)
class MatchResult:
    job_id: str
    match_score: float
    rationale: str


def _parse_match_response(text: str) -> tuple[float, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise TypeError("match response must be a JSON object")
    score = float(data.get("match_score", 0))
    rationale = str(data.get("rationale", ""))
    return max(0.0, min(1.0, score)), rationale


def rank_job(job: JobPosting, profile: ResumeProfile, *, llm: LLMProvider) -> MatchResult:
    prompt = json.dumps(
        {
            "job": job.model_dump(mode="json"),
            "resume": {
                "name": profile.name,
                "skills": profile.skills,
                "experience": profile.experience,
                "summary": profile.summary,
            },
        },
        indent=2,
    )
    response = llm.complete(
        system=(
            "Score job fit vs resume from 0.0 to 1.0. Return JSON: "
            '{"match_score": float, "rationale": string} only.'
        ),
        user=prompt,
    )
    score, rationale = _parse_match_response(response)
    return MatchResult(job_id=job.job_id, match_score=score, rationale=rationale)


def rank_jobs(
    jobs: list[JobPosting],
    profile: ResumeProfile,
    *,
    llm: LLMProvider,
) -> list[MatchResult]:
    results = [rank_job(job, profile, llm=llm) for job in jobs]
    return sorted(results, key=lambda r: r.match_score, reverse=True)
