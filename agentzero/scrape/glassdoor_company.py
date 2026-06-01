"""Resolve Glassdoor employer names from URLs, HTML, and job descriptions."""

from __future__ import annotations

import re

_JOB_LISTING_SLUG_RE = re.compile(r"/job-listing/(.+?)-JV_", re.IGNORECASE)
_EMPLOYER_JSON_RE = re.compile(
    r'"employerName"\s*:\s*"(?P<name>(?:\\.|[^"\\])*)"',
    re.IGNORECASE,
)
_COMPANY_JSON_RE = re.compile(
    r'"companyName"\s*:\s*"(?P<name>(?:\\.|[^"\\])*)"',
    re.IGNORECASE,
)
_OPENINGS_FOR_RE = re.compile(
    r"^(?P<company>.{2,120}?)\s+has (?:multiple )?openings for\b",
    re.IGNORECASE,
)
_ARE_WITH_RE = re.compile(
    r"\bare with\s+(?P<company>.{2,120}?)\.",
    re.IGNORECASE,
)
_IS_THE_RE = re.compile(
    r"(?:^|[.!?]\s+)(?P<company>[A-Z][\w&.'/-]{2,80}?)\s+is (?:the|a|an)\b",
)
_WHO_ARE_WE_RE = re.compile(
    r"Who Are We\?\s*(?P<company>.{2,80}?)\s+is\b",
    re.IGNORECASE,
)
_ORG_NAME_RE = re.compile(r"\b(CALSTART|Volusia County Schools)\b", re.IGNORECASE)
_KNOWN_DESCRIPTION_EMPLOYERS = (
    "Lockheed Martin Space",
    "Lockheed Martin",
    "TEKsystems",
    "Northrop Grumman",
)
_AT_COMPANY_RE = re.compile(
    r"\bat\s+(?P<company>[A-Z][\w&.,'/-]{2,80}?)\s*,\s*we\b",
    re.IGNORECASE,
)


def slugify_title(title: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return re.sub(r"-+", "-", cleaned)


def titleize_slug(slug: str) -> str:
    parts = [part for part in slug.split("-") if part]
    if not parts:
        return ""
    return " ".join(part.capitalize() for part in parts)


def company_from_glassdoor_job_url(url: str, *, title: str) -> str | None:
    """Parse employer from canonical Glassdoor job-listing URL slugs."""
    match = _JOB_LISTING_SLUG_RE.search(url)
    if not match:
        return None
    slug = match.group(1).lower().strip("/")
    title_slug = slugify_title(title)
    if title_slug and slug.startswith(f"{title_slug}-"):
        company_slug = slug[len(title_slug) + 1 :]
        company = titleize_slug(company_slug)
        return company or None
    return None


def company_from_glassdoor_html(html: str, *, title: str, url: str = "") -> str | None:
    """Best-effort employer extraction from a Glassdoor job or search page."""
    from_url = company_from_glassdoor_job_url(url, title=title) if url else None
    if from_url:
        return from_url

    for pattern in (_EMPLOYER_JSON_RE, _COMPANY_JSON_RE):
        match = pattern.search(html)
        if match:
            name = _unescape_json(match.group("name")).strip()
            if _looks_like_company(name, title=title):
                return name

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    soup = BeautifulSoup(html, "html.parser")
    employer = soup.select_one('[data-test="employer-name"], .EmployerProfile')
    if employer is not None:
        name = employer.get_text(strip=True)
        if _looks_like_company(name, title=title):
            return name
    return None


def company_from_glassdoor_description(description: str, *, title: str) -> str | None:
    """Parse employer from fetched Glassdoor posting description text."""
    if not description.strip():
        return None
    text = description
    if "<" in description:
        try:
            from bs4 import BeautifulSoup

            text = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
        except ImportError:
            text = re.sub(r"<[^>]+>", " ", description)
    text = re.sub(r"\s+", " ", text).strip()
    match = _OPENINGS_FOR_RE.search(text)
    if match:
        company = match.group("company").strip(" .")
        if _looks_like_company(company, title=title):
            return company
    match = _ARE_WITH_RE.search(text)
    if match:
        company = match.group("company").strip(" .")
        if _looks_like_company(company, title=title):
            return company
    match = _WHO_ARE_WE_RE.search(text)
    if match:
        company = match.group("company").strip(" .")
        if _looks_like_company(company, title=title):
            return company
    match = _IS_THE_RE.search(text)
    if match:
        company = match.group("company").strip(" .")
        if _looks_like_company(company, title=title):
            return company
    org_match = _ORG_NAME_RE.search(text)
    if org_match:
        name = org_match.group(1).strip()
        return "CALSTART" if name.upper() == "CALSTART" else name
    match = _AT_COMPANY_RE.search(text)
    if match:
        company = match.group("company").strip(" .")
        if _looks_like_company(company, title=title):
            return company
    for employer in _KNOWN_DESCRIPTION_EMPLOYERS:
        if employer in text:
            return employer
    return None


def resolve_glassdoor_company(
    *,
    title: str,
    url: str = "",
    html: str = "",
    description: str = "",
) -> str | None:
    """Try all Glassdoor employer resolution strategies in priority order."""
    for resolver, kwargs in (
        (company_from_glassdoor_description, {"description": description, "title": title}),
        (company_from_glassdoor_html, {"html": html, "title": title, "url": url}),
        (company_from_glassdoor_job_url, {"url": url, "title": title}),
    ):
        if not kwargs.get("description") and not kwargs.get("html") and not kwargs.get("url"):
            continue
        company = resolver(**kwargs)  # type: ignore[arg-type]
        if company:
            return company
    return None


def _looks_like_company(name: str, *, title: str) -> bool:
    cleaned = name.strip()
    if len(cleaned) < 2 or len(cleaned) > 120:
        return False
    if cleaned.casefold() == title.casefold():
        return False
    if cleaned.lower() in {"unknown", "confidential", "company"}:
        return False
    return True


def _unescape_json(value: str) -> str:
    return value.replace("\\u0026", "&").replace('\\"', '"').replace("\\\\", "\\")
