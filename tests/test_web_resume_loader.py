from pathlib import Path
from unittest.mock import MagicMock, patch

from agentzero.ingest.search_profile import ResumeSearchProfile
from agentzero.web.resume_loader import (
    ResumeLoader,
    latest_resume_info,
    load_resume_search_profile,
)


def test_latest_resume_info_missing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    info = latest_resume_info(resume_dir)
    assert info["available"] is False


def test_latest_resume_info_found(tmp_path: Path):
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    (resume_dir / "cv.pdf").write_bytes(b"%PDF-1.4")
    info = latest_resume_info(resume_dir)
    assert info["available"] is True
    assert info["filename"] == "cv.pdf"


def test_load_resume_search_profile_no_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume").mkdir()
    ok, msg, terms = load_resume_search_profile()
    assert ok is False
    assert "No résumé" in msg
    assert terms == []


def test_load_resume_search_profile_success(tmp_path: Path, monkeypatch):
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    (resume_dir / "cv.txt").write_text("engineer", encoding="utf-8")
    profile = ResumeSearchProfile(
        search_terms=["Software Engineer"],
        locations=["Remote"],
        source_resume_path=str(resume_dir / "cv.txt"),
        source_fingerprint="abc",
        updated_at="2026-01-01T00:00:00Z",
    )
    with (
        patch(
            "agentzero.web.resume_loader.find_latest_resume",
            return_value=resume_dir / "cv.txt",
        ),
        patch(
            "agentzero.web.resume_loader.resolve_search_from_resume",
            return_value=profile,
        ),
        patch("agentzero.llm.provider.build_llm_provider", return_value=MagicMock()),
    ):
        ok, msg, terms = load_resume_search_profile()
    assert ok is True
    assert terms == ["Software Engineer"]
    assert "cv.txt" in msg


def test_resume_loader_selects_all_titles_on_first_load(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "web_operator_config.json"
    loader = ResumeLoader()

    def fake_load(**_k):
        return True, "ok", ["A", "B"]

    monkeypatch.setattr("agentzero.web.resume_loader.load_resume_search_profile", fake_load)
    ok, _ = loader.start(cfg_path)
    assert ok is True
    import time

    deadline = time.time() + 2
    while time.time() < deadline and loader.state.running:
        time.sleep(0.05)
    from agentzero.web.operator_config import load_operator_config

    saved = load_operator_config(cfg_path)
    assert saved is not None
    assert saved.search_terms == ["A", "B"]
