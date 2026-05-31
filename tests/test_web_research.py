"""Tests for web-search enrichment parsers and HTML parsing."""

from pathlib import Path

from agentzero.enrich.snippet_parse import (
    parse_company_size_from_text,
    parse_glassdoor_from_text,
)
from agentzero.enrich.web_research import (
    extract_careers_urls,
    title_keywords,
)
from agentzero.enrich.web_search import SearchHit, parse_duckduckgo_html

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_glassdoor_from_snippet():
    text = "Netflix - Glassdoor — 4.2 ★ · 12,345 reviews · Company size 1,001-5,000 employees"
    rating, reviews = parse_glassdoor_from_text(text)
    assert rating == 4.2
    assert reviews == 12345


def test_parse_glassdoor_named_reviews():
    text = "30 Bitwarden reviews. A free inside look at company reviews."
    _rating, reviews = parse_glassdoor_from_text(text)
    assert reviews == 30


def test_parse_glassdoor_out_of_five():
    text = "Employees rated Bitwarden 4.1 out of 5 on Glassdoor. 39 reviews."
    rating, reviews = parse_glassdoor_from_text(text)
    assert rating == 4.1
    assert reviews == 39


def test_parse_company_size_range():
    assert parse_company_size_from_text("LinkedIn · 201-500 employees") == "201-500"
    assert parse_company_size_from_text("Growing team of 75 employees") == "51-200"


def test_parse_duckduckgo_html_fixture():
    html = (FIXTURES / "ddg_sample.html").read_text(encoding="utf-8")
    hits = parse_duckduckgo_html(html, max_results=5)
    assert len(hits) >= 2
    assert any("glassdoor" in hit.url.lower() for hit in hits)


def test_extract_careers_urls_prefers_company_boards():
    hits = [
        SearchHit(
            title="Careers at Acme",
            url="https://boards.greenhouse.io/acme",
            snippet="Open roles",
        ),
        SearchHit(
            title="Acme Jobs | LinkedIn",
            url="https://www.linkedin.com/jobs/view/123",
            snippet="",
        ),
    ]
    urls = extract_careers_urls(hits, company="Acme")
    assert urls[0].startswith("https://boards.greenhouse.io")


def test_title_keywords_filters_noise():
    words = title_keywords("Senior Security Engineer (Remote)")
    assert "security" in words
    assert "senior" not in words
    assert "engineer" not in words
    assert "remote" not in words
