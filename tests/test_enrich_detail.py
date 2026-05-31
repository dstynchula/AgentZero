"""Detail fetch parsing and merge."""

from __future__ import annotations

from agentzero.enrich.detail_fetch import fetch_job_detail_html, merge_detail_fields
from agentzero.enrich.detail_parse import parse_linkedin_job_detail_html
from agentzero.enrich.gaps import needs_enrichment_pass
from agentzero.models import JobPosting


def _job(**kwargs) -> JobPosting:
    base = dict(
        title="Security Engineer",
        company="Acme Corp",
        url="https://www.linkedin.com/jobs/view/123",
        source="linkedin",
    )
    base.update(kwargs)
    return JobPosting(**base)


def test_parse_linkedin_detail_description():
    html = """
    <html><body>
    <div class="show-more-less-html__markup">
    We need a security engineer. Salary $140,000 - $180,000 per year.
 250 employees worldwide.
    </div></body></html>
    """
    fields = parse_linkedin_job_detail_html(html)
    assert "security engineer" in fields["description"]
    assert fields.get("comp_min") == 140_000
    assert fields.get("company_size_hint") == 250


def test_parse_linkedin_detail_comp_from_insight_still_finds_employees():
    """Comp from salary insight must not skip page_text (employee count lives elsewhere)."""
    html = """
    <html><body>
    <span class="job-details-jobs-unified-top-card__job-insight-view-model-secondary">
      $200K/yr - $240K/yr
    </span>
    <div class="show-more-less-html__markup">
    Join our team. We have 1,500+ employees globally.
    </div></body></html>
    """
    fields = parse_linkedin_job_detail_html(html)
    assert fields.get("comp_min") == 200_000
    assert fields.get("company_size_hint") == 1500


def test_merge_detail_fields_does_not_overwrite():
    job = _job(comp_min=100_000, description="old")
    merged = merge_detail_fields(
        job,
        {"description": "new long text", "comp_min": 50_000, "comp_max": 60_000},
    )
    assert merged.description == "old"
    assert merged.comp_min == 100_000


def test_needs_enrichment_pass_linkedin_listing():
    job = _job()
    assert needs_enrichment_pass(job)


def test_fetch_job_detail_html_blocks_localhost():
    from agentzero.config import Settings

    job = _job(url="http://127.0.0.1/admin")
    settings = Settings(_env_file=None)
    assert fetch_job_detail_html(job, settings=settings, allow_browser=False) is None
