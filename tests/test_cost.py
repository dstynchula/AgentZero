import json

from agentzero.config import Settings
from agentzero.cost.estimate import (
    PRICING_AS_OF,
    estimate_run_cost,
    estimate_unique_jobs,
)
from agentzero.ingest.resume import ResumeProfile
from agentzero.ingest.search_profile import (
    clear_search_profile_session_cache,
    resolve_search_from_resume,
)
from agentzero.models import JobPosting
from agentzero.rank.matcher import _job_payload_for_ranking, rank_job


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, *, system: str, user: str) -> str:
        self.calls += 1
        return json.dumps(
            {
                "recent_roles": [{"title": "Engineer", "company": "Co"}],
                "search_terms": ["Engineer"],
                "locations": ["Remote"],
            }
        )


def test_estimate_run_cost_gpt5_nano_is_cents():
    est = estimate_run_cost(model="gpt-5-nano", ranked_jobs=100)
    assert est.usd_mid < 0.10
    assert est.pricing_as_of == PRICING_AS_OF


def test_estimate_unique_jobs_single_query():
    settings = Settings(_env_file=None, search_terms=["a"], locations=["Remote"], results_wanted=50)
    low, high = estimate_unique_jobs(settings)
    assert low >= 35
    assert high == 50


def test_search_profile_session_cache_avoids_duplicate_llm(tmp_path, monkeypatch):
    clear_search_profile_session_cache()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "agentzero.config.get_settings",
        lambda: Settings(_env_file=None, db_path=data_dir / "agentzero.db"),
    )
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    (resume_dir / "r.txt").write_text("resume body for cache test", encoding="utf-8")
    llm = FakeLLM()
    resolve_search_from_resume(llm=llm, resume_dir=resume_dir)
    resolve_search_from_resume(llm=llm, resume_dir=resume_dir)
    assert llm.calls == 1
    clear_search_profile_session_cache()


def test_job_payload_truncates_description():
    long_desc = "x" * 5000
    job = JobPosting(
        title="T",
        company="C",
        url="https://x.com",
        source="indeed",
        description=long_desc,
    )
    payload = _job_payload_for_ranking(job, max_description_chars=100)
    assert len(payload["description"]) < 200
    assert "truncated" in payload["description"]


def test_rank_job_uses_truncation(monkeypatch):
    job = JobPosting(
        title="T",
        company="C",
        url="https://x.com",
        source="indeed",
        description="d" * 4000,
    )
    profile = ResumeProfile(raw_text="x", skills=[], experience=[], source_path="")
    seen: list[str] = []

    class CaptureLLM:
        def complete(self, *, system: str, user: str) -> str:
            seen.append(user)
            return json.dumps({"match_score": 0.5, "rationale": "ok"})

    rank_job(job, profile, llm=CaptureLLM(), max_description_chars=50)
    assert "truncated" in seen[0]
