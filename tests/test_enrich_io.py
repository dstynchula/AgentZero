"""P26e: detail_fetch, company_research, glassdoor_company coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentzero.config import Settings
from agentzero.enrich.company_research import (
    CompanyFactsCache,
    CompanyWebFacts,
    _company_key,
    _facts_incomplete,
    _merge_glassdoor,
    _merge_size,
    enrich_job_web_research,
    research_company,
)
from agentzero.enrich.detail_fetch import (
    _browser_site_for_job,
    fetch_and_merge_detail,
    fetch_details_batch,
    fetch_job_detail_html,
    merge_detail_fields,
)
from agentzero.enrich.glassdoor_company import (
    enrich_glassdoor_company,
    fetch_glassdoor_company_html,
    glassdoor_search_url,
    parse_glassdoor_from_page,
)
from agentzero.enrich.web_search import SearchHit
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


def test_browser_site_for_job():
    assert _browser_site_for_job(_job(url="https://www.linkedin.com/jobs/1")) == "linkedin"
    assert _browser_site_for_job(_job(url="https://indeed.com/viewjob")) == "indeed"
    assert _browser_site_for_job(_job(url="https://glassdoor.com/job/1")) == "glassdoor"
    assert _browser_site_for_job(_job(url="https://example.com/j")) is None


def test_merge_detail_fields_fills_gaps():
    job = _job(company="unknown", description=None, comp_min=None, comp_max=None)
    merged = merge_detail_fields(
        job,
        {
            "description": "Long enough description text",
            "company": "Acme Corp",
            "comp_min": 140_000,
            "comp_max": 180_000,
            "currency": "USD",
            "company_size_hint": 250,
        },
    )
    assert merged.description == "Long enough description text"
    assert merged.company == "Acme Corp"
    assert merged.comp_min == 140_000
    assert merged.comp_is_estimate is True
    assert merged.company_size == "201-500"


def test_fetch_job_detail_html_http_short_falls_back_disabled():
    settings = Settings(_env_file=None)
    job = _job(url="https://example.com/job")
    with patch(
        "agentzero.enrich.detail_fetch.safe_get_text",
        return_value="<html>short</html>",
    ):
        assert fetch_job_detail_html(job, settings=settings, allow_browser=False) == "<html>short</html>"


def test_fetch_job_detail_html_uses_browser_for_linkedin():
    settings = Settings(_env_file=None)
    job = _job()
    long_html = "<html>" + ("x" * 600) + "</html>"
    with (
        patch("agentzero.enrich.detail_fetch.safe_get_text", return_value=None),
        patch("agentzero.enrich.detail_fetch._fetch_html_browser", return_value=long_html) as browser,
    ):
        result = fetch_job_detail_html(job, settings=settings, allow_browser=True)
    assert result == long_html
    browser.assert_called_once()


def test_fetch_html_browser_blocks_unsafe_url():
    settings = Settings(_env_file=None)
    with patch(
        "agentzero.enrich.detail_fetch.validate_fetch_url",
        side_effect=__import__("agentzero.net.url_safety", fromlist=["UnsafeURLError"]).UnsafeURLError("blocked"),
    ):
        from agentzero.enrich.detail_fetch import _fetch_html_browser

        assert _fetch_html_browser("http://127.0.0.1/x", settings=settings, site="linkedin") is None


def test_fetch_and_merge_detail_http():
    settings = Settings(_env_file=None)
    job = _job(description=None)
    html = "<html>" + ("desc " * 200) + "</html>"
    with (
        patch("agentzero.enrich.detail_fetch.fetch_job_detail_html", return_value=html),
        patch(
            "agentzero.enrich.detail_fetch.parse_job_detail_html",
            return_value={"description": "parsed description"},
        ),
    ):
        merged = fetch_and_merge_detail(job, settings=settings, allow_browser=False)
    assert merged.description == "parsed description"


def test_fetch_details_batch(monkeypatch):
    settings = Settings(_env_file=None)
    jobs = [_job(url="https://x.com/1"), _job(url="https://x.com/2", title="Staff")]
    sleeps: list[float] = []
    monkeypatch.setattr("agentzero.enrich.detail_fetch.time.sleep", lambda s: sleeps.append(s))
    with patch(
        "agentzero.enrich.detail_fetch.fetch_and_merge_detail",
        side_effect=lambda job, **kw: job.model_copy(update={"description": "d"}),
    ):
        out = fetch_details_batch(jobs, settings=settings, delay_seconds=0.5)
    assert len(out) == 2
    assert sleeps == [0.5]


def test_company_research_helpers():
    facts = CompanyWebFacts()
    _merge_size(facts, "51-200")
    _merge_glassdoor(facts, 4.2, 100)
    assert facts.company_size == "51-200"
    assert facts.glassdoor_rating == 4.2
    assert not _facts_incomplete(facts)
    assert _company_key("  Acme  Corp ") == "acme corp"


def test_research_company_mocks_search():
    settings = Settings(_env_file=None, enrich_web_search_max_results=3, enrich_web_search_delay_seconds=0)
    hits = [
        SearchHit(
            title="Acme Glassdoor",
            url="https://www.glassdoor.com/Reviews/acme.htm",
            snippet="4.1 out of 5 · 50 reviews · 201-500 employees",
        ),
        SearchHit(
            title="Careers",
            url="https://boards.greenhouse.io/acme",
            snippet="Join Acme",
        ),
    ]
    with (
        patch("agentzero.enrich.company_research.search_web", return_value=hits),
        patch("agentzero.enrich.company_research.safe_get_text", return_value=None),
    ):
        facts = research_company("Acme Corp", settings=settings)
    assert facts.glassdoor_rating == 4.1
    assert facts.company_size == "201-500"
    assert facts.glassdoor_reviews == 50


def test_company_facts_cache_thread_safe():
    settings = Settings(_env_file=None, enrich_web_search_delay_seconds=0)
    cache = CompanyFactsCache()
    facts = CompanyWebFacts(company_size="51-200")
    with patch("agentzero.enrich.company_research.research_company", return_value=facts) as research:
        first = cache.get("Acme", settings=settings)
        second = cache.get("Acme", settings=settings)
    assert first is second
    research.assert_called_once()


def test_enrich_job_web_research_with_dict_cache():
    settings = Settings(_env_file=None, enrich_web_search_delay_seconds=0)
    job = _job(company_size=None, glassdoor_rating=None)
    facts = CompanyWebFacts(
        company_size="51-200",
        glassdoor_rating=4.0,
        glassdoor_reviews=10,
        careers_urls=["https://boards.greenhouse.io/acme"],
    )
    cache: dict = {}
    with (
        patch("agentzero.enrich.company_research.research_company", return_value=facts),
        patch(
            "agentzero.enrich.company_research.pick_verified_careers_url",
            return_value="https://boards.greenhouse.io/acme",
        ),
    ):
        merged = enrich_job_web_research(job, settings=settings, cache=cache)
    assert merged.company_size == "51-200"
    assert merged.glassdoor_rating == 4.0
    assert merged.careers_url == "https://boards.greenhouse.io/acme"
    assert "acme corp" in cache


def test_enrich_job_web_research_no_updates():
    settings = Settings(_env_file=None)
    job = _job(company_size="51-200", glassdoor_rating=4.5, glassdoor_reviews=20, careers_url="https://acme.com/jobs")
    facts = CompanyWebFacts()
    with patch("agentzero.enrich.company_research.research_company", return_value=facts):
        assert enrich_job_web_research(job, settings=settings) is job


def test_glassdoor_search_url():
    assert "Acme+Corp" in glassdoor_search_url("Acme Corp")


def test_parse_glassdoor_from_page_json_fallback():
    html = '{"rating": 4.3, "reviewCount": 88}'
    rating, reviews = parse_glassdoor_from_page(html)
    assert rating == 4.3
    assert reviews == 88


def test_enrich_glassdoor_company_skips_when_complete():
    job = _job(glassdoor_rating=4.0, glassdoor_reviews=10)
    assert enrich_glassdoor_company(job, user_agent="ua") is job


def test_enrich_glassdoor_company_skips_unknown():
    job = _job(company="unknown")
    assert enrich_glassdoor_company(job, user_agent="ua") is job


def test_enrich_glassdoor_company_applies_rating():
    job = _job(glassdoor_rating=None, glassdoor_reviews=None)
    html = '{"rating": 4.5, "reviewCount": 120}'
    with patch("agentzero.enrich.glassdoor_company.fetch_glassdoor_company_html", return_value=html):
        merged = enrich_glassdoor_company(job, user_agent="ua")
    assert merged.glassdoor_rating == 4.5
    assert merged.glassdoor_reviews == 120


def test_fetch_glassdoor_company_html():
    with patch("agentzero.enrich.glassdoor_company.safe_get_text", return_value="<html/>") as get:
        html = fetch_glassdoor_company_html("Acme", user_agent="ua")
    assert html == "<html/>"
    get.assert_called_once()

def test_fetch_html_browser_success_and_cleanup():
    settings = Settings(_env_file=None)
    page = MagicMock()
    page.url = "https://www.linkedin.com/jobs/view/1"
    page.content.return_value = "<html>" + ("x" * 600) + "</html>"
    context = MagicMock()
    playwright = MagicMock()
    with (
        patch("agentzero.enrich.detail_fetch.validate_fetch_url"),
        patch(
            "agentzero.scrape.browser_common.launch_browser_page",
            return_value=(playwright, context, page),
        ),
    ):
        from agentzero.enrich.detail_fetch import _fetch_html_browser

        html = _fetch_html_browser("https://www.linkedin.com/jobs/view/1", settings=settings, site="linkedin")
    assert html is not None
    context.close.assert_called_once()
    playwright.stop.assert_called_once()


def test_fetch_html_browser_unsafe_landing_url():
    settings = Settings(_env_file=None)
    page = MagicMock()
    page.url = "http://127.0.0.1/internal"
    context = MagicMock()
    playwright = MagicMock()
    with (
        patch("agentzero.enrich.detail_fetch.validate_fetch_url"),
        patch(
            "agentzero.scrape.browser_common.launch_browser_page",
            return_value=(playwright, context, page),
        ),
        patch(
            "agentzero.enrich.detail_fetch.validate_fetch_url",
            side_effect=[None, __import__("agentzero.net.url_safety", fromlist=["UnsafeURLError"]).UnsafeURLError("bad")],
        ),
    ):
        from agentzero.enrich.detail_fetch import _fetch_html_browser

        assert _fetch_html_browser("https://www.linkedin.com/jobs/1", settings=settings, site="linkedin") is None


def test_enrich_glassdoor_company_fetch_failed():
    job = _job(glassdoor_rating=None)
    with patch("agentzero.enrich.glassdoor_company.fetch_glassdoor_company_html", return_value=None):
        assert enrich_glassdoor_company(job, user_agent="ua") is job
