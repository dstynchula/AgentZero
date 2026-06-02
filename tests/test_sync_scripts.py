"""Tests for CLI helpers (run_scrape)."""

from __future__ import annotations


def test_run_scrape_skip_ingest_without_snapshot(tmp_path, monkeypatch):
    import scripts.run_scrape as run_scrape_mod

    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume").mkdir()
    code = run_scrape_mod.run(
        limit=5,
        skip_resume_ingest=True,
        search_prompt=False,
        refresh_search=False,
        verbose=False,
    )
    assert code == 1
