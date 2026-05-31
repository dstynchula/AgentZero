import json
from pathlib import Path

from agentzero.ingest.resume import ExperienceEntry
from agentzero.ingest.search_profile import (
    clear_search_profile_session_cache,
    extract_search_profile,
    load_matching_search_profile,
    prioritize_search_terms,
    resolve_search_from_resume,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append(system)
        return json.dumps(self.payload)


def test_prioritize_search_terms_puts_recent_roles_first():
    roles = [
        ExperienceEntry(title="Staff Engineer", company="Acme", is_current=True),
        ExperienceEntry(title="Software Engineer", company="StartupCo"),
    ]
    llm_terms = ["Software Engineer", "Platform Engineer", "Backend Developer"]
    terms = prioritize_search_terms(roles, llm_terms)
    assert terms[0] == "Staff Engineer"
    assert terms[1] == "Software Engineer"
    assert "Platform Engineer" in terms
    assert terms.index("Staff Engineer") < terms.index("Platform Engineer")


def test_extract_search_profile_orders_terms_by_recent_roles(tmp_path):
    resume = tmp_path / "resume.txt"
    resume.write_text("Senior SWE at Acme", encoding="utf-8")
    llm = FakeLLM(
        {
            "recent_roles": [
                {"title": "Senior Software Engineer", "company": "Acme", "is_current": True},
                {"title": "Software Engineer", "company": "StartupCo"},
            ],
            "search_terms": ["Backend Developer", "Senior Software Engineer", "Data Engineer"],
            "locations": ["Remote"],
        }
    )
    profile = extract_search_profile("text", resume_path=resume, llm=llm)
    assert profile.search_terms[0] == "Senior Software Engineer"
    assert profile.search_terms[1] == "Software Engineer"
    assert profile.recent_roles[0].title == "Senior Software Engineer"


def test_resolve_search_from_resume_writes_snapshot(tmp_path):
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    (resume_dir / "mine.txt").write_text("resume body", encoding="utf-8")
    llm = FakeLLM(
        {
            "recent_roles": [{"title": "Product Engineer", "company": "Beta"}],
            "search_terms": ["Full Stack Engineer"],
            "locations": ["San Francisco, CA"],
        }
    )
    profile = resolve_search_from_resume(llm=llm, resume_dir=resume_dir)
    snapshot = resume_dir / "search_profile.json"
    assert snapshot.is_file()
    assert profile.search_terms[0] == "Product Engineer"


def test_load_matching_search_profile_uses_snapshot(tmp_path):
    clear_search_profile_session_cache()
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    resume = resume_dir / "mine.txt"
    resume.write_text("resume body", encoding="utf-8")
    llm = FakeLLM(
        {
            "recent_roles": [{"title": "Engineer", "company": "Co"}],
            "search_terms": ["Engineer"],
            "locations": ["Remote"],
        }
    )
    first = resolve_search_from_resume(llm=llm, resume_dir=resume_dir)
    assert load_matching_search_profile(resume_dir) == first

    class ExplodingLLM:
        def complete(self, *, system: str, user: str) -> str:
            raise AssertionError("should not call LLM when snapshot matches")

    second = resolve_search_from_resume(llm=ExplodingLLM(), resume_dir=resume_dir)  # type: ignore[arg-type]
    assert second.search_terms == first.search_terms
