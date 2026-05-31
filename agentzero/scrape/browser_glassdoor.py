"""Parse Glassdoor job search HTML."""

from __future__ import annotations

import json
import re

from agentzero.models import RawRecord

GLASSDOOR_BASE = "https://www.glassdoor.com"

_JOB_MARKERS = (
    "jobListing",
    "JobsList",
    "job-listing",
    "react-job-listing",
    "JobCard",
)

_CAPTCHA_MARKERS = (
    "captcha",
    "cf-turnstile",
    "blocked",
    "access denied",
    "ray id",
    "__cf_chl",
    "challenge-platform",
)

_LOGIN_URL_MARKERS = (
    "login_input",
    "/profile/login",
    "/auth/login",
    "signin",
)

_LOGIN_HTML_MARKERS = (
    "sign in to glassdoor",
    "log in to glassdoor",
    'type="password"',
    "login-email",
)


def page_has_job_results(html: str) -> bool:
    return any(marker in html for marker in _JOB_MARKERS)


def page_session_ready(html: str, url: str = "") -> bool:
    if page_has_job_results(html):
        return True
    url_lower = url.lower()
    if "/member/" in url_lower:
        return True
    if "/profile/" in url_lower and "login" not in url_lower:
        return True
    return False


def page_needs_login(html: str, url: str = "") -> bool:
    if page_session_ready(html, url):
        return False
    url_lower = url.lower()
    if any(marker in url_lower for marker in _LOGIN_URL_MARKERS):
        return True
    if page_has_job_results(html):
        return False
    html_lower = html.lower()
    return any(marker in html_lower for marker in _LOGIN_HTML_MARKERS)


def page_needs_human(html: str, url: str = "") -> bool:
    if page_has_job_results(html):
        return False
    if page_needs_login(html, url):
        return False
    html_lower = html.lower()
    return any(marker in html_lower for marker in _CAPTCHA_MARKERS)


def build_glassdoor_search_url(*, term: str, parsed: object) -> str:
    from urllib.parse import quote_plus

    from agentzero.scrape.location import ParsedLocation

    assert isinstance(parsed, ParsedLocation)
    loc = parsed.jobspy_location
    keyword = quote_plus(term)
    loc_kw = quote_plus(loc)
    url = (
        f"{GLASSDOOR_BASE}/Job/jobs.htm?"
        f"sc.keyword={keyword}&locT=N&locId=1&locKeyword={loc_kw}"
    )
    if parsed.is_remote:
        url += "&remoteWorkType=1"
    return url


def _records_from_next_data(html: str, *, source: str) -> list[RawRecord]:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    records: list[RawRecord] = []
    seen: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            title = node.get("jobTitleText") or node.get("jobTitle")
            company = node.get("employerName") or node.get("companyName")
            listing_id = node.get("jobListingId") or node.get("listingId")
            if title and company and listing_id:
                key = str(listing_id)
                if key not in seen:
                    seen.add(key)
                    url = node.get("jobViewUrl") or f"{GLASSDOOR_BASE}/job-listing/j?jl={listing_id}"
                    loc = node.get("locationName") or node.get("location")
                    record: RawRecord = {
                        "title": str(title),
                        "company": str(company),
                        "url": str(url),
                        "source": source,
                    }
                    if loc:
                        record["location"] = str(loc)
                    records.append(record)
            elif title and listing_id and not company:
                key = str(listing_id)
                if key not in seen:
                    seen.add(key)
                    url = node.get("jobViewUrl") or f"{GLASSDOOR_BASE}/job-listing/j?jl={listing_id}"
                    from agentzero.scrape.glassdoor_company import company_from_glassdoor_job_url

                    resolved = company_from_glassdoor_job_url(str(url), title=str(title))
                    record = {
                        "title": str(title),
                        "company": resolved or "Unknown",
                        "url": str(url),
                        "source": source,
                    }
                    loc = node.get("locationName") or node.get("location")
                    if loc:
                        record["location"] = str(loc)
                    records.append(record)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return records


def parse_glassdoor_search_html(html: str, *, source: str = "glassdoor") -> list[RawRecord]:
    embedded = _records_from_next_data(html, source=source)
    if embedded:
        return embedded

    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ImportError("Glassdoor parsing requires beautifulsoup4.") from exc

    soup = BeautifulSoup(html, "html.parser")
    records: list[RawRecord] = []
    seen: set[str] = set()

    cards = soup.select(
        'li[data-test="jobListing"], li.react-job-listing, div[data-test="job-card"], article.JobCard'
    )
    for card in cards:
        link = card.select_one('a[data-test="job-link"]') or card.find("a", href=True)
        if link is None:
            continue
        href = link.get("href", "")
        if not href:
            continue
        url = href if href.startswith("http") else f"{GLASSDOOR_BASE}{href}"
        if url in seen:
            continue
        seen.add(url)

        title_el = card.select_one('[data-test="job-title"]') or link
        title = title_el.get_text(strip=True) if title_el else ""
        if len(title) < 2:
            continue

        company_el = card.select_one('[data-test="employer-name"]') or card.select_one(
            ".EmployerProfile"
        )
        company = company_el.get_text(strip=True) if company_el else "Unknown"
        if company == "Unknown":
            from agentzero.scrape.glassdoor_company import company_from_glassdoor_job_url

            resolved = company_from_glassdoor_job_url(url, title=title)
            if resolved:
                company = resolved
        location_el = card.select_one('[data-test="emp-location"]')
        location = location_el.get_text(strip=True) if location_el else None

        record: RawRecord = {
            "title": title,
            "company": company,
            "url": url,
            "source": source,
        }
        if location:
            record["location"] = location
        records.append(record)

    return records
