import json

import pytest

from agentzero.config import Settings
from agentzero.generate.cover_letter import (
    COVER_LETTER_SYSTEM_PROMPT,
    MAX_COVER_LETTER_CHARS,
    cover_letter_path,
    generate_cover_letter,
    generate_cover_letter_text,
    read_cover_letter,
    save_cover_letter,
)
from agentzero.llm.provider import OpenAIProvider, build_cover_letter_provider
from tests.test_db import _job


class FakeCoverLLM:
    def __init__(self, text: str = "Dear hiring team,\n\nI led security programs at Acme.") -> None:
        self.text = text
        self.last_system: str | None = None
        self.last_user: str | None = None

    def complete(self, *, system: str, user: str) -> str:
        self.last_system = system
        self.last_user = user
        return self.text


def test_cover_letter_uses_gpt_5_5_model():
    settings = Settings(_env_file=None, openai_api_key="sk-test", cover_letter_model="gpt-5.5")
    provider = build_cover_letter_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-5.5"


def test_build_cover_letter_provider_rejects_anthropic():
    settings = Settings(
        _env_file=None,
        llm_provider="anthropic",
        anthropic_api_key="sk-ant",
    )
    with pytest.raises(ValueError, match="openai"):
        build_cover_letter_provider(settings)


def test_generate_cover_letter_writes_output_file(tmp_path):
    job = _job(description="Build secure APIs.")
    llm = FakeCoverLLM()
    out_dir = tmp_path / "letters"
    path = generate_cover_letter(job, "Jane Doe\nStaff engineer at TrueCar.", llm=llm, base_dir=out_dir)
    assert path == cover_letter_path(job.job_id, base_dir=out_dir)
    assert path.read_text(encoding="utf-8") == llm.text
    assert read_cover_letter(job.job_id, base_dir=out_dir) == llm.text


def test_read_and_save_cover_letter_round_trip(tmp_path):
    job = _job()
    out_dir = tmp_path / "letters"
    save_cover_letter(job.job_id, "Edited letter body.", base_dir=out_dir)
    assert read_cover_letter(job.job_id, base_dir=out_dir) == "Edited letter body."


def test_save_rejects_empty_and_oversized(tmp_path):
    job = _job()
    out_dir = tmp_path / "letters"
    with pytest.raises(ValueError, match="empty"):
        save_cover_letter(job.job_id, "   ", base_dir=out_dir)
    with pytest.raises(ValueError, match="exceeds"):
        save_cover_letter(job.job_id, "x" * (MAX_COVER_LETTER_CHARS + 1), base_dir=out_dir)


def test_prompt_includes_fact_based_neutral_instructions():
    job = _job(title="Staff Security Engineer", company="Acme Corp", description="Own AppSec.")
    llm = FakeCoverLLM()
    generate_cover_letter_text(job, "Resume body with TrueCar experience.", llm=llm)
    assert llm.last_system == COVER_LETTER_SYSTEM_PROMPT
    assert "fact-based" in llm.last_system
    assert "No truisms" in llm.last_system
    payload = json.loads(llm.last_user or "{}")
    assert payload["job"]["title"] == "Staff Security Engineer"
    assert "Resume body" in payload["resume_text"]


def test_rejects_empty_llm_response():
    job = _job()
    llm = FakeCoverLLM(text="   ")
    with pytest.raises(ValueError, match="empty"):
        generate_cover_letter_text(job, "resume text", llm=llm)
