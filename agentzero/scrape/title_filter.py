"""Reject scraped listings whose titles don't match the configured search profile."""

from __future__ import annotations

import re

from agentzero.models import JobPosting

# Generic role/level words stripped from AGENTZERO_SEARCH_TERMS before matching.
ROLE_STOPWORDS = frozenset(
    {
        "and",
        "director",
        "engineer",
        "engineering",
        "for",
        "ii",
        "iii",
        "iv",
        "junior",
        "l4",
        "l5",
        "lead",
        "level",
        "manager",
        "mid",
        "of",
        "or",
        "principal",
        "remote",
        "senior",
        "sr",
        "staff",
        "the",
        "usa",
        "us",
    }
)

# Obvious non-fit titles (marketing, HR, sales, etc.) even when a board returns them.
TITLE_DISQUALIFY_RE = re.compile(
    r"\b(?:"
    r"marketing|human resources|talent acquisition|recruiting coordinator|"
    r"account executive|business development|customer success|"
    r"product manager|brand manager|content strategist|copywriter|"
    r"public relations|communications director|"
    r"\bhr\b"
    r")\b",
    re.IGNORECASE,
)


def search_keywords(search_terms: list[str]) -> set[str]:
    """Domain terms from search strings (e.g. ``staff security engineer`` → ``security``)."""
    words: set[str] = set()
    for term in search_terms:
        for word in re.findall(r"[a-z0-9]{3,}", term.lower()):
            if word not in ROLE_STOPWORDS:
                words.add(word)
    return words


def title_matches_search(title: str, search_terms: list[str]) -> bool:
    """True when *title* plausibly matches the configured search terms."""
    if TITLE_DISQUALIFY_RE.search(title):
        return False
    keywords = search_keywords(search_terms)
    if not keywords:
        return True
    title_lower = title.lower()
    return any(re.search(rf"\b{re.escape(keyword)}\b", title_lower) for keyword in keywords)


def filter_by_title_relevance(
    jobs: list[JobPosting],
    search_terms: list[str],
) -> tuple[list[JobPosting], list[JobPosting]]:
    """Split jobs into title-relevant vs rejected."""
    if not search_terms:
        return jobs, []
    kept: list[JobPosting] = []
    rejected: list[JobPosting] = []
    for job in jobs:
        if title_matches_search(job.title, search_terms):
            kept.append(job)
        else:
            rejected.append(job)
    return kept, rejected
