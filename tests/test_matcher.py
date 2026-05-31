import json

from agentzero.ingest.resume import ExperienceEntry, ResumeProfile
from agentzero.models import JobPosting
from agentzero.rank.matcher import (
    RANK_JOB_FIELDS,
    MatchResult,
    _job_payload_for_ranking,
    rank_job,
    rank_jobs,
)


class FakeLLM:
    def __init__(self, score: float = 0.85) -> None:
        self.score = score

    def complete(self, *, system: str, user: str) -> str:
        return json.dumps({"match_score": self.score, "rationale": "Strong skill overlap"})


def test_rank_job_returns_score():
    job = JobPosting(
        title="Backend Engineer",
        company="Acme",
        url="https://x.com/1",
        source="indeed",
    )
    profile = ResumeProfile(raw_text="python", skills=["Python"], experience=[], source_path="")
    result = rank_job(job, profile, llm=FakeLLM(0.9))
    assert isinstance(result, MatchResult)
    assert result.match_score == 0.9
    assert result.job_id == job.job_id


def test_rank_job_serializes_experience_entries():
    job = JobPosting(
        title="Staff Security Engineer",
        company="Acme",
        url="https://x.com/1",
        source="indeed",
    )
    profile = ResumeProfile(
        raw_text="resume",
        skills=["Python"],
        experience=[
            ExperienceEntry(title="Senior Security Engineer", company="TrueCar", is_current=False)
        ],
        source_path="resume/test.docx",
    )
    result = rank_job(job, profile, llm=FakeLLM(0.75))
    assert result.match_score == 0.75


def test_rank_jobs_sorted_descending():
    jobs = [
        JobPosting(title="A", company="C", url="https://x.com/1", source="indeed"),
        JobPosting(title="B", company="C", url="https://x.com/2", source="indeed"),
    ]
    profile = ResumeProfile(raw_text="x", skills=[], experience=[], source_path="")
    results = rank_jobs(jobs, profile, llm=FakeLLM(0.5))
    assert results[0].match_score >= results[1].match_score


def test_rank_payload_omits_tracker_metadata():
    job = JobPosting(
        title="Engineer",
        company="Acme",
        url="https://example.com/job/1",
        source="indeed",
        notes="internal note",
        careers_url="https://careers.example.com",
        match_score=0.5,
    )
    payload = _job_payload_for_ranking(job, max_description_chars=500)
    assert set(payload.keys()).issubset(RANK_JOB_FIELDS)
    assert "url" not in payload
    assert "notes" not in payload
    assert "careers_url" not in payload
    assert "match_score" not in payload
