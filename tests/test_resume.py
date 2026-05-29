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
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, *, system: str, user: str) -> str:
        return json.dumps(self.payload)


def test_read_resume_text_from_txt():
    text = read_resume_text(FIXTURES / "sample_resume.txt")
    assert "Jane Doe" in text


def test_extract_resume_profile_parses_llm_json():
    llm = FakeLLM(
        {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "skills": ["Python"],
            "experience": ["Engineer at ExampleCorp"],
            "summary": "Backend engineer",
        }
    )
    profile = extract_resume_profile("raw resume text", llm=llm)
    assert profile.name == "Jane Doe"
    assert profile.skills == ["Python"]


def test_ingest_resume_from_directory(tmp_path):
    sample = FIXTURES / "sample_resume.txt"
    dest = tmp_path / "resume" / "mine.txt"
    dest.parent.mkdir(parents=True)
    dest.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    llm = FakeLLM(
        {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "skills": ["Python"],
            "experience": ["Engineer"],
            "summary": "Backend",
        }
    )
    profile = ingest_resume(llm=llm, resume_dir=tmp_path / "resume")
    assert isinstance(profile, ResumeProfile)
    assert profile.source_path.endswith("mine.txt")


def test_ingest_resume_missing_dir_raises(tmp_path):
    llm = FakeLLM({})
    with pytest.raises(FileNotFoundError):
        ingest_resume(llm=llm, resume_dir=tmp_path / "empty")
