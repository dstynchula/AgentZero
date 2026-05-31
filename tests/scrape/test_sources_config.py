from pathlib import Path

from agentzero.scrape.parse_list import parse_list_page_html
from agentzero.scrape.sources_config import (
    JobSourceEntry,
    JobSourcesFile,
    load_job_sources,
    resolve_jobspy_sites,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONFIG = Path(__file__).resolve().parents[2] / "docs" / "examples" / "job_sources.json"


def test_load_job_sources_parses_config():
    cfg = load_job_sources(CONFIG)
    assert cfg is not None
    assert cfg.job_sources == []
    assert cfg.jobspy_sites == []


def test_resolve_jobspy_sites_expands_all():
    sites = resolve_jobspy_sites(["all"], job_sources=None)
    assert "google" in sites
    assert "indeed" in sites
    assert "linkedin" in sites


def test_resolve_jobspy_sites_merges_json():
    cfg = JobSourcesFile(jobspy_sites=["glassdoor"])
    sites = resolve_jobspy_sites(["google"], job_sources=cfg)
    assert sites == ["google", "glassdoor"]


def test_build_search_url_encodes_query():
    entry = JobSourceEntry(
        name="Test Board",
        url="https://example.com/",
        search_url_template="https://example.com/jobs?q={query}&l={location}",
    )
    url = entry.build_search_url(query="security engineer", location="Remote, CA")
    assert "security" in url
    assert "Remote" in url


def test_parse_list_page_html_extracts_jobs():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    entry = JobSourceEntry(
        name="Cyber Board",
        url="https://cyber.example.com/",
        search_url_template="https://cyber.example.com/jobs?q={query}",
        selectors={
            "job_card": "article.job-listing",
            "title_link": "a[href*='/jobs/']",
            "company": ".company",
            "location": ".location",
        },
    )
    records = parse_list_page_html(
        html,
        entry=entry,
        page_url="https://cyber.example.com/jobs?q=security",
    )
    assert len(records) == 2
    assert records[0]["title"] == "Staff Security Engineer"
    assert records[0]["company"] == "Acme Corp"
    assert records[0]["url"] == "https://cyber.example.com/jobs/staff-security-engineer"
    assert records[0]["source"] == "cyber_board"


def test_load_job_sources_missing_returns_none(tmp_path: Path):
    assert load_job_sources(tmp_path / "missing.json") is None
