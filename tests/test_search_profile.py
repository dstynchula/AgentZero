import json
import stat
from pathlib import Path

from agentzero.config import Settings
from agentzero.ingest.resume import ExperienceEntry
from agentzero.ingest.search_profile import (
    clear_search_profile_session_cache,
    extract_search_profile,
    load_matching_search_profile,
    load_search_profile,
    prioritize_search_terms,
    resolve_search_from_resume,
    save_search_profile,
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


def test_resolve_search_from_resume_writes_snapshot(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "agentzero.config.get_settings",
        lambda: Settings(_env_file=None, db_path=data_dir / "agentzero.db"),
    )
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
    snapshot = data_dir / "search_profile.json"
    assert snapshot.is_file()
    assert not (resume_dir / "search_profile.json").exists()
    assert profile.search_terms[0] == "Product Engineer"


def test_save_search_profile_writes_under_data_dir(tmp_path):
    settings = Settings(_env_file=None, db_path=tmp_path / "data" / "agentzero.db")
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    from agentzero.ingest.search_profile import ResumeSearchProfile

    snap = ResumeSearchProfile(
        search_terms=["Engineer"],
        locations=["Remote"],
        source_resume_path="resume/x.txt",
        source_fingerprint="fp",
        updated_at="2026-01-01T00:00:00Z",
    )
    path = save_search_profile(snap, resume_dir, settings=settings)
    assert path == tmp_path / "data" / "search_profile.json"
    assert path.is_file()


def test_load_search_profile_falls_back_to_resume_dir(tmp_path):
    settings = Settings(_env_file=None, db_path=tmp_path / "data" / "agentzero.db")
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    legacy = {
        "search_terms": ["Legacy Role"],
        "locations": ["Remote"],
        "source_resume_path": "resume/old.txt",
        "source_fingerprint": "abc",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    (resume_dir / "search_profile.json").write_text(json.dumps(legacy), encoding="utf-8")
    loaded = load_search_profile(resume_dir, settings=settings)
    assert loaded is not None
    assert loaded.search_terms == ["Legacy Role"]


def test_save_succeeds_when_resume_dir_read_only(tmp_path):
    settings = Settings(_env_file=None, db_path=tmp_path / "data" / "agentzero.db")
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    if hasattr(stat, "S_IWRITE"):
        resume_dir.chmod(stat.S_IREAD | stat.S_IEXEC)
    from agentzero.ingest.search_profile import ResumeSearchProfile

    snap = ResumeSearchProfile(
        search_terms=["Engineer"],
        locations=["Remote"],
        source_resume_path="resume/x.txt",
        source_fingerprint="fp",
        updated_at="2026-01-01T00:00:00Z",
    )
    path = save_search_profile(snap, resume_dir, settings=settings)
    assert path.is_file()
    resume_dir.chmod(stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)


def test_load_matching_search_profile_uses_snapshot(tmp_path, monkeypatch):
    clear_search_profile_session_cache()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "agentzero.config.get_settings",
        lambda: Settings(_env_file=None, db_path=data_dir / "agentzero.db"),
    )
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
