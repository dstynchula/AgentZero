"""Parallel browser detail enrichment in batch runner."""

from __future__ import annotations

import threading

from agentzero.config import Settings
from agentzero.enrich.batch import run_enrich_batch
from agentzero.models import JobPosting
from agentzero.storage.db import Database


def _job(**kwargs) -> JobPosting:
    base = dict(
        title="Platform Engineer",
        company="Acme",
        url="https://www.linkedin.com/jobs/view/123",
        source="linkedin",
        description="Short.",
    )
    base.update(kwargs)
    return JobPosting(**base)


def test_run_enrich_batch_uses_parallel_browser_pool_when_configured(
    tmp_path, monkeypatch
):
    db = Database(tmp_path / "t.db")
    job = _job()
    db.upsert_job(job)
    settings = Settings(
        _env_file=None,
        enrich_browser_max_concurrency=5,
        enrich_max_concurrency=2,
        enrich_web_search=False,
    )
    active = 0
    peak = 0
    lock = threading.Lock()

    def _deep(job, **kwargs):
        nonlocal active, peak
        if kwargs.get("allow_browser"):
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                return job.model_copy(update={"description": "Full description text." * 20})
            finally:
                with lock:
                    active -= 1
        return job

    monkeypatch.setattr("agentzero.enrich.batch.enrich_job_deep", _deep)
    monkeypatch.setattr(
        "agentzero.enrich.batch.needs_detail_fetch",
        lambda j: True,
    )

    result = run_enrich_batch(
        db,
        [job.job_id],
        settings=settings,
        max_workers=2,
        fetch_detail=True,
        glassdoor_lookup=False,
        web_search=False,
        allow_browser=True,
        browser_delay_seconds=0,
    )
    assert result.total == 1
    assert peak <= 5
