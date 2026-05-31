"""LLM-based job vs résumé matching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentzero.ingest.resume import ResumeProfile
from agentzero.models import JobPosting

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

# Fields sent to the rank LLM (omit tracker metadata, URLs, and long notes).
RANK_JOB_FIELDS = frozenset(
    {
        "title",
        "company",
        "source",
        "location",
        "remote",
        "comp_min",
        "comp_max",
        "comp_is_estimate",
        "company_size",
        "glassdoor_rating",
        "description",
    }
)


@dataclass(frozen=True, slots=True)
class MatchResult:
    job_id: str
    match_score: float
    rationale: str


def _parse_match_response(text: str) -> tuple[float, str]:
    from agentzero.llm.json_util import parse_llm_json_object

    data = parse_llm_json_object(text)
    score = float(data.get("match_score", 0))
    rationale = str(data.get("rationale", ""))
    return max(0.0, min(1.0, score)), rationale


def _job_payload_for_ranking(job: JobPosting, *, max_description_chars: int) -> dict:
    """Shrink rank prompts: relevant fields only + truncated description."""
    data = job.model_dump(mode="json", include=RANK_JOB_FIELDS)
    description = data.get("description")
    if (
        isinstance(description, str)
        and max_description_chars > 0
        and len(description) > max_description_chars
    ):
        data["description"] = (
            description[:max_description_chars] + "… [truncated for ranking cost]"
        )
    return data


def rank_job(
    job: JobPosting,
    profile: ResumeProfile,
    *,
    llm: LLMProvider,
    max_description_chars: int | None = None,
) -> MatchResult:
    if max_description_chars is None:
        from agentzero.config import get_settings

        max_description_chars = get_settings().rank_description_max_chars

    prompt = json.dumps(
        {
            "job": _job_payload_for_ranking(job, max_description_chars=max_description_chars),
            "resume": profile.model_dump(
                mode="json",
                include={"name", "skills", "experience", "summary"},
            ),
        },
        default=str,
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
    max_description_chars: int | None = None,
) -> list[MatchResult]:
    results = [
        rank_job(job, profile, llm=llm, max_description_chars=max_description_chars)
        for job in jobs
    ]
    return sorted(results, key=lambda r: r.match_score, reverse=True)
