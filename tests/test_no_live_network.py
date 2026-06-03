"""Unit tests must not perform live HTTP (DuckDuckGo, Glassdoor, job boards)."""

from __future__ import annotations

import time
from unittest.mock import patch

from agentzero.config import Settings
from agentzero.enrich import web_search
from agentzero.enrich.pipeline import enrich_job
from agentzero.models import JobPosting


def test_search_web_stubbed_by_default():
    hits = web_search.search_web("Acme Corp glassdoor", max_results=3, user_agent="test-agent")
    assert hits == []


def test_safe_get_text_not_used_by_enrich_job_by_default():
    """enrich_job with web search off must not call outbound HTTP."""
    calls: list[str] = []

    def track(*args, **kwargs):
        calls.append("safe_get_text")
        return None

    job = JobPosting(
        title="Engineer",
        company="Acme",
        url="https://jobs.example.com/1",
        source="indeed",
        description="Salary $120k-150k. 120 employees. Glassdoor rating: 4.1",
    )
    settings = Settings(_env_file=None, enrich_web_search=False)
    with patch("agentzero.net.http_client.safe_get_text", side_effect=track):
        enrich_job(job, settings=settings)
    assert calls == []


def test_enrich_job_runs_all_steps_completes_under_one_second():
    job = JobPosting(
        title="Engineer",
        company="Acme",
        url="https://jobs.example.com/1",
        source="indeed",
        description="Salary $120k-150k. 120 employees. Glassdoor rating: 4.1",
    )
    settings = Settings(_env_file=None, enrich_web_search=False)
    started = time.perf_counter()
    enriched = enrich_job(job, settings=settings)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0
    assert enriched.comp_min == 120_000
    assert enriched.company_size == "51-200"
    assert enriched.glassdoor_rating == 4.1
