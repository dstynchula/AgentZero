"""Tests for title relevance filtering."""

from __future__ import annotations

from agentzero.models import JobPosting
from agentzero.scrape.title_filter import (
    filter_by_title_relevance,
    search_keywords,
    title_matches_search,
)


def _job(title: str) -> JobPosting:
    return JobPosting(title=title, company="Acme", url="https://example.com/j", source="test")


def test_search_keywords_from_security_engineer_query():
    assert search_keywords(["staff security engineer"]) == {"security"}


def test_title_matches_security_roles():
    terms = ["staff security engineer"]
    assert title_matches_search("Senior Security Engineer", terms)
    assert title_matches_search("Principal Security Engineer - REMOTE", terms)


def test_title_rejects_marketing_and_hr():
    terms = ["staff security engineer"]
    assert not title_matches_search("VP of Marketing", terms)
    assert not title_matches_search("Vice President, Human Resources", terms)


def test_filter_by_title_relevance():
    terms = ["staff security engineer"]
    jobs = [
        _job("Security Engineer"),
        _job("VP of Marketing"),
        _job("Vice President, Human Resources"),
    ]
    kept, rejected = filter_by_title_relevance(jobs, terms)
    assert len(kept) == 1
    assert len(rejected) == 2
    assert kept[0].title == "Security Engineer"
