"""Tests for interactive search targeting."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentzero.config import Settings
from agentzero.ingest.search_interactive import (
    format_search_summary,
    interactive_refine_search_profile,
    prepare_run_search,
)
from agentzero.ingest.search_profile import (
    ResumeSearchProfile,
    clear_search_profile_session_cache,
    load_search_profile,
)


def _sample_profile(resume_path: Path) -> ResumeSearchProfile:
    return ResumeSearchProfile(
        search_terms=["Staff Security Engineer", "Principal Security Engineer"],
        locations=["Remote", "Los Angeles, CA"],
        source_resume_path=str(resume_path),
        source_fingerprint="abc123",
        updated_at="2026-01-01T00:00:00Z",
        salary_min=180_000.0,
    )


def test_format_search_summary_includes_salary():
    profile = _sample_profile(Path("resume/test.docx"))
    profile = profile.model_copy(update={"remote_preferred": True})
    text = format_search_summary(profile)
    assert "Staff Security Engineer" in text
    assert "Remote" in text
    assert "$180,000" in text
    assert "Comp floor" in text


def test_interactive_refine_keeps_remote_on_empty_input(tmp_path):
    resume = tmp_path / "resume" / "r.docx"
    resume.parent.mkdir(parents=True)
    resume.write_bytes(b"x")
    profile = _sample_profile(resume).model_copy(
        update={"locations": ["remote - usa"], "remote_preferred": True}
    )
    # ack, titles, mode, comp floor, confirm
    inputs = iter(["", "", "", "", "yes"])

    refined = interactive_refine_search_profile(
        profile,
        interactive=True,
        input_fn=lambda _: next(inputs),
        resume_dir=tmp_path / "resume",
    )

    assert refined.search_terms == profile.search_terms
    assert refined.locations == ["remote - usa"]
    assert refined.remote_preferred is True
    assert refined.salary_min == profile.salary_min
    assert load_search_profile(tmp_path / "resume") is not None


def test_interactive_refine_applies_user_edits(tmp_path):
    resume = tmp_path / "resume" / "r.docx"
    resume.parent.mkdir(parents=True)
    resume.write_bytes(b"x")
    profile = _sample_profile(resume)
    inputs = iter(
        [
            "",
            "Security Architect, CISO",
            "r",
            "230000",
            "yes",
        ]
    )

    refined = interactive_refine_search_profile(
        profile,
        interactive=True,
        input_fn=lambda _: next(inputs),
        resume_dir=tmp_path / "resume",
    )

    assert refined.search_terms == ["Security Architect", "CISO"]
    assert refined.locations == ["remote - usa"]
    assert refined.remote_preferred is True
    assert refined.salary_min == 230_000.0
    assert refined.salary_max is None


def test_interactive_refine_skipped_when_disabled(tmp_path):
    profile = _sample_profile(tmp_path / "r.docx")
    refined = interactive_refine_search_profile(profile, interactive=False)
    assert refined is profile


def test_interactive_refine_cancelled_by_user(tmp_path):
    profile = _sample_profile(tmp_path / "r.docx")
    inputs = iter(["", "", "", "", "", "n"])
    with pytest.raises(KeyboardInterrupt, match="cancelled"):
        interactive_refine_search_profile(
            profile,
            interactive=True,
            input_fn=lambda _: next(inputs),
        )


def test_interactive_refine_clears_floor_with_none(tmp_path):
    profile = _sample_profile(tmp_path / "r.docx")
    inputs = iter(["", "", "r", "none", "yes"])
    refined = interactive_refine_search_profile(
        profile,
        interactive=True,
        input_fn=lambda _: next(inputs),
    )
    assert refined.salary_min is None


def test_interactive_refine_rejects_empty_confirm(tmp_path):
    profile = _sample_profile(tmp_path / "r.docx")
    inputs = iter(["", "", "r", "", "", "yes"])
    refined = interactive_refine_search_profile(
        profile,
        interactive=True,
        input_fn=lambda _: next(inputs),
    )
    assert refined.search_terms == profile.search_terms


def test_prepare_run_search_merges_into_settings(tmp_path, monkeypatch):
    clear_search_profile_session_cache()
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    resume = resume_dir / "r.docx"
    resume.write_bytes(b"resume bytes")

    profile = _sample_profile(resume)

    class FakeLLM:
        def complete(self, system: str, user: str) -> str:
            raise AssertionError("should use session cache / resolve path")

    monkeypatch.setattr(
        "agentzero.ingest.search_profile.load_matching_search_profile",
        lambda resume_dir=None: None,
    )
    monkeypatch.setattr(
        "agentzero.ingest.search_interactive.resolve_search_from_resume",
        lambda **kwargs: profile,
    )

    settings = Settings(
        _env_file=None,
        search_interactive=False,
        results_wanted=25,
    )
    effective, returned = prepare_run_search(
        settings,
        llm=FakeLLM(),  # type: ignore[arg-type]
        interactive=False,
    )

    assert returned.search_terms == profile.search_terms
    assert effective.search_terms == profile.search_terms
    assert effective.locations == ["remote - usa"]
    assert effective.remote_preferred is True
    assert effective.salary_min == 180_000.0
    assert effective.results_wanted == 25
