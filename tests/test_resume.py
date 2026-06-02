import json
from pathlib import Path

import pytest

from agentzero.ingest.resume import (
    ResumeProfile,
    extract_resume_profile,
    ingest_resume,
    read_resume_text,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    def __init__(self, profile_payload: dict, search_payload: dict | None = None) -> None:
        self.profile_payload = profile_payload
        self.search_payload = search_payload or {
            "recent_roles": [{"title": "Engineer", "company": "Co", "is_current": True}],
            "search_terms": ["Software Engineer"],
            "locations": ["Remote"],
        }

    def complete(self, *, system: str, user: str) -> str:
        if "job-search" in system or "search parameters" in system:
            return json.dumps(self.search_payload)
        return json.dumps(self.profile_payload)


def test_read_resume_text_from_txt():
    text = read_resume_text(FIXTURES / "sample_resume.txt")
    assert "Jane Doe" in text


def test_extract_resume_profile_parses_llm_json():
    llm = FakeLLM(
        {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "skills": ["Python"],
            "experience": [
                {"title": "Senior Engineer", "company": "ExampleCorp", "is_current": True},
                {"title": "Engineer", "company": "StartupCo"},
            ],
            "summary": "Backend engineer",
        }
    )
    profile = extract_resume_profile("raw resume text", llm=llm)
    assert profile.name == "Jane Doe"
    assert profile.experience[0].title == "Senior Engineer"
    assert profile.experience[0].is_current is True


def test_extract_resume_profile_coerces_string_experience():
    llm = FakeLLM(
        {
            "name": "Jane",
            "experience": ["Engineer at ExampleCorp"],
            "skills": [],
        }
    )
    profile = extract_resume_profile("raw", llm=llm)
    assert profile.experience[0].title == "Engineer at ExampleCorp"


def test_ingest_resume_from_directory(tmp_path, monkeypatch):
    from agentzero.config import Settings

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "agentzero.config.get_settings",
        lambda: Settings(_env_file=None, db_path=data_dir / "agentzero.db"),
    )
    sample = FIXTURES / "sample_resume.txt"
    dest = tmp_path / "resume" / "mine.txt"
    dest.parent.mkdir(parents=True)
    dest.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    llm = FakeLLM(
        {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "skills": ["Python"],
            "experience": [{"title": "Engineer", "company": "Co"}],
            "summary": "Backend",
        }
    )
    profile = ingest_resume(llm=llm, resume_dir=tmp_path / "resume")
    assert isinstance(profile, ResumeProfile)
    assert profile.source_path.endswith("mine.txt")
    assert (data_dir / "search_profile.json").is_file()


def test_ingest_resume_missing_dir_raises(tmp_path):
    llm = FakeLLM({})
    with pytest.raises(FileNotFoundError):
        ingest_resume(llm=llm, resume_dir=tmp_path / "empty")
