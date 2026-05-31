"""Careers-page URL discovery and verification from web search hits."""

from __future__ import annotations

import re

from agentzero.enrich.web_search import SearchHit
from agentzero.net.http_client import safe_get_text

CAREERS_URL_RE = re.compile(
    r"(careers|/jobs|greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs|"
    r"workdayjobs|smartrecruiters|jobvite|icims|bamboohr|recruiting)",
    re.IGNORECASE,
)

ATS_HOSTS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workday.com",
    "smartrecruiters.com",
)

SKIP_URL_RE = re.compile(
    r"(linkedin\.com/(?:jobs|company)|indeed\.com|glassdoor\.com/job|ziprecruiter\.com|"
    r"google\.com/search|facebook\.com|twitter\.com|x\.com|jobtoday\.com|builtin\w*\.com|"
    r"wellfound\.com|jobalmanac\.com|ziprecruiter|simplyhired|monster\.com)",
    re.IGNORECASE,
)

LOW_QUALITY_CAREERS_RE = re.compile(
    r"(jobtoday|builtin\w*\.com|linkedin\.com/company|indeed\.com/cmp|wellfound|"
    r"glassdoor\.com/Job|jobalmanac|uwcu\.org|ziprecruiter)",
    re.IGNORECASE,
)

TITLE_STOPWORDS = frozenset(
    {
        "and", "for", "the", "with", "remote", "senior", "staff", "principal",
        "lead", "engineer", "engineering", "usa", "us", "u", "s", "ii", "iii",
        "iv", "l5", "l4",
    }
)


def _company_slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]", "", company.lower())


def title_keywords(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", title.lower())
    return {w for w in words if w not in TITLE_STOPWORDS}


def is_low_quality_careers_url(url: str, company: str) -> bool:
    if not url or LOW_QUALITY_CAREERS_RE.search(url):
        return True
    lowered = url.lower()
    if any(ats in lowered for ats in ATS_HOSTS):
        return False
    slug = _company_slug(company)
    if len(slug) < 4:
        return False
    host_path = lowered.replace("-", "").replace(".", "").replace("/", "")
    return slug not in host_path


def score_careers_url(url: str, company: str) -> int:
    lowered = url.lower()
    if SKIP_URL_RE.search(url):
        return -100
    score = 0
    if CAREERS_URL_RE.search(lowered):
        score += 2
    slug = _company_slug(company)
    if any(host in lowered for host in ATS_HOSTS):
        if slug and slug not in lowered.replace("-", "").replace(".", "").replace("/", ""):
            return -50
        score += 4
    if "careers." in lowered or "/careers" in lowered:
        score += 2
    if slug and slug in lowered.replace("-", "").replace(".", ""):
        score += 3
    return score


def extract_careers_urls(hits: list[SearchHit], *, company: str) -> list[str]:
    """Rank candidate careers / jobs board URLs from search hits."""
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []
    for hit in hits:
        url = hit.url
        if SKIP_URL_RE.search(url) or not CAREERS_URL_RE.search(url):
            continue
        norm = url.split("#")[0].rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        score = score_careers_url(norm, company)
        if score > 0:
            scored.append((score, norm))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [url for _, url in scored]


def fetch_page_text(url: str, *, user_agent: str, max_chars: int = 80_000) -> str | None:
    html = safe_get_text(url, user_agent=user_agent, max_chars=max_chars)
    if not html:
        return None
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def careers_page_lists_role(url: str, title: str, *, user_agent: str) -> bool:
    text = fetch_page_text(url, user_agent=user_agent)
    if not text:
        return False
    lowered = text.lower()
    keywords = title_keywords(title)
    if not keywords:
        return title.lower() in lowered
    hits = sum(1 for kw in keywords if kw in lowered)
    return hits >= min(2, len(keywords))


def pick_verified_careers_url(
    company: str,
    title: str,
    candidates: list[str],
    *,
    user_agent: str,
) -> str | None:
    good = [u for u in candidates if not is_low_quality_careers_url(u, company)]
    for url in good[:5]:
        try:
            if careers_page_lists_role(url, title, user_agent=user_agent):
                return url
        except Exception:
            continue
    for url in good:
        if score_careers_url(url, company) >= 4:
            return url
    return None
