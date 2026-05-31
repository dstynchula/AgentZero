"""Indeed job search via Playwright (real browser — avoids many 400/429 blocks)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import quote_plus

from agentzero.models import RawRecord

log = logging.getLogger(__name__)

INDEED_BASE = "https://www.indeed.com"
MOSAIC_MARKER = 'window.mosaic.providerData["mosaic-provider-jobcards"]'
InputFn = Callable[[str], str]

_JOB_RESULT_MARKERS = (
    "mosaic-provider-jobcards",
    "mosaicProviderJobCardsModel",
    "job_seen_beacon",
    'data-jk="',
    'data-testid="jobTitle"',
    "jobsearch-NoResults",
)

_CAPTCHA_MARKERS = (
    "cf-turnstile",
    "recaptcha",
    "challenge-form",
    "hcaptcha",
    "verify you are human",
    "additional verification",
    "unusual traffic",
    "robot check",
    "ray id",  # Cloudflare / Indeed block page after CAPTCHA
    "performance & security by cloudflare",
    "checking your browser",
    "just a moment",
    "please enable cookies",
    "access denied",
)

_LOGIN_HTML_MARKERS = (
    "ready to take the next step",
    "create an account or sign in",
    "continue with google",
    "continue with apple",
    'name="__email"',
    'name="email"',
)


def _default_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def page_session_ready(html: str, url: str = "") -> bool:
    if page_has_job_results(html):
        return True
    url_lower = url.lower()
    if "www.indeed.com" not in url_lower or "secure.indeed.com" in url_lower:
        return False
    if "/account/login" in url_lower or "/auth" in url_lower:
        return False
    if "/jobs" in url_lower:
        return False
    return True


def page_needs_login(html: str, url: str = "") -> bool:
    """Return True on Indeed account sign-in pages (not CAPTCHA blocks)."""
    if page_session_ready(html, url):
        return False
    url_lower = url.lower()
    if "secure.indeed.com" in url_lower:
        return True
    if "/account/login" in url_lower:
        return True
    if "/auth" in url_lower and "indeed.com" in url_lower:
        return True
    if page_has_job_results(html):
        return False
    html_lower = html.lower()
    return any(marker in html_lower for marker in _LOGIN_HTML_MARKERS)


def page_needs_human(html: str, url: str = "") -> bool:
    """Return True when the page looks like a CAPTCHA or block screen."""
    url_lower = url.lower()
    if any(token in url_lower for token in ("indeed.com/sorry", "/captcha", "/challenge")):
        return True
    html_lower = html.lower()
    if page_has_job_results(html):
        return False
    if page_needs_login(html, url):
        return False
    if any(marker in html_lower for marker in _CAPTCHA_MARKERS):
        return True
    # Stale block page: CAPTCHA cleared but body is only a Ray ID / sorry message.
    if "sorry" in html_lower and "indeed" in html_lower and len(html) < 25_000:
        return True
    return False


def page_has_job_results(html: str) -> bool:
    """Return True when Indeed search results (or explicit no-results) are present."""
    return any(token in html for token in _JOB_RESULT_MARKERS)


def extract_mosaic_payload(html: str) -> dict[str, Any] | None:
    """Pull the embedded Indeed job-cards JSON from page HTML."""
    marker = MOSAIC_MARKER
    idx = html.find(marker)
    if idx < 0:
        marker = "window.mosaic.providerData['mosaic-provider-jobcards']"
        idx = html.find(marker)
    if idx < 0:
        return None

    eq = html.find("=", idx)
    if eq < 0:
        return None
    start = html.find("{", eq)
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    quote_char = ""

    for i in range(start, len(html)):
        ch = html[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote_char:
                in_string = False
            continue

        if ch in {'"', "'"}:
            in_string = True
            quote_char = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def mosaic_results_to_records(
    data: dict[str, Any],
    *,
    source: str = "indeed",
    remote_search: bool = False,
) -> list[RawRecord]:
    """Convert mosaic JSON payload to raw scrape records."""
    model = (
        data.get("metaData", {})
        .get("mosaicProviderJobCardsModel", {})
    )
    results = model.get("results") or []
    records: list[RawRecord] = []

    for job in results:
        if not isinstance(job, dict):
            continue
        title = (
            job.get("displayTitle")
            or job.get("title")
            or job.get("normTitle")
            or job.get("jobTitle")
        )
        company = job.get("company") or job.get("companyName")
        jobkey = job.get("jobkey") or job.get("jobKey")
        if not title or not company or not jobkey:
            continue

        record: RawRecord = {
            "title": str(title).strip(),
            "company": str(company).strip(),
            "url": f"{INDEED_BASE}/viewjob?jk={jobkey}",
            "source": source,
        }
        location = job.get("formattedLocation") or job.get("jobLocationCity")
        if location:
            record["location"] = str(location).strip()
        if job.get("remoteLocation"):
            record["remote"] = True

        from agentzero.scrape.remote_policy import apply_remote_search_trust_to_record

        apply_remote_search_trust_to_record(record, remote_search=remote_search)

        snippet = job.get("salarySnippet") or {}
        if isinstance(snippet, dict):
            salary_text = snippet.get("text") or snippet.get("salaryText")
            if salary_text:
                record["comp_raw"] = str(salary_text).strip()

        rating = job.get("companyRating")
        if rating is not None:
            record["glassdoor_rating"] = float(rating)
        reviews = job.get("companyReviewCount")
        if reviews is not None:
            record["glassdoor_reviews"] = int(reviews)

        records.append(record)

    return records


def parse_indeed_mosaic_html(
    html: str,
    *,
    source: str = "indeed",
    remote_search: bool = False,
) -> list[RawRecord]:
    payload = extract_mosaic_payload(html)
    if payload is None:
        return []
    return mosaic_results_to_records(payload, source=source, remote_search=remote_search)


def prompt_for_browser_verification(
    *,
    reason: str,
    input_fn: InputFn | None = None,
) -> None:
    """Ask the user to complete CAPTCHA/consent in the visible browser."""
    read = input_fn or _default_input
    print("\n" + "=" * 60)
    print("Indeed browser — action needed")
    print("=" * 60)
    print(reason)
    print("Complete any block/consent in the Chromium window, then press Enter here.")
    print("=" * 60)
    read("Press Enter when ready… ")


def build_indeed_search_url(*, term: str, parsed: object) -> str:
    from agentzero.scrape.location import ParsedLocation

    assert isinstance(parsed, ParsedLocation)
    query = quote_plus(term)
    loc = quote_plus(parsed.browser_location)
    url = f"{INDEED_BASE}/jobs?q={query}&l={loc}"
    if parsed.is_remote:
        url += "&remotejob=1"
    return url


def parse_indeed_search_html(
    html: str,
    *,
    source: str = "indeed",
    remote_search: bool = False,
) -> list[RawRecord]:
    """Parse Indeed search results from embedded JSON, then DOM fallback."""
    records = parse_indeed_mosaic_html(html, source=source, remote_search=remote_search)
    if records:
        return records
    return _parse_indeed_dom_html(html, source=source, remote_search=remote_search)


def _parse_indeed_dom_html(
    html: str,
    *,
    source: str = "indeed",
    remote_search: bool = False,
) -> list[RawRecord]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ImportError(
            "Indeed HTML parsing requires beautifulsoup4. pip install -e '.[scrape]'"
        ) from exc

    soup = BeautifulSoup(html, "html.parser")
    records: list[RawRecord] = []

    cards = soup.select('[data-testid="slider_item"], div.job_seen_beacon, div[data-jk]')
    seen: set[str] = set()

    for card in cards:
        title_link = (
            card.select_one('[data-testid="jobTitle"] a')
            or card.select_one("h2.jobTitle a")
            or card.select_one("a.jcs-JobTitle")
            or card.select_one("a[data-jk]")
        )
        if title_link is None:
            continue
        title = title_link.get_text(strip=True)
        href = title_link.get("href", "")
        jobkey = card.get("data-jk") or title_link.get("data-jk")
        if href.startswith("/"):
            url = f"{INDEED_BASE}{href}"
        elif href.startswith("http"):
            url = href
        elif jobkey:
            url = f"{INDEED_BASE}/viewjob?jk={jobkey}"
        else:
            continue

        dedupe_key = jobkey or url
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        company_el = (
            card.select_one('[data-testid="company-name"]')
            or card.select_one("span.companyName")
            or card.select_one('[data-testid="attribute_snippet_testid"]')
        )
        company = company_el.get_text(strip=True) if company_el else "Unknown"
        location_el = card.select_one('[data-testid="text-location"]') or card.select_one(
            "div.companyLocation"
        )
        location = location_el.get_text(strip=True) if location_el else None
        record: RawRecord = {
            "title": title,
            "company": company,
            "url": url,
            "source": source,
        }
        if location:
            record["location"] = location
        from agentzero.scrape.remote_policy import apply_remote_search_trust_to_record

        apply_remote_search_trust_to_record(record, remote_search=remote_search)
        records.append(record)

    return records


def _dismiss_indeed_consent(page: object) -> None:
    """Click common cookie/consent buttons if present."""
    for selector in (
        "button#onetrust-accept-btn-handler",
        'button:has-text("Accept")',
        'button:has-text("Accept All")',
    ):
        try:
            btn = page.locator(selector).first  # type: ignore[union-attr]
            if btn.is_visible(timeout=2_000):
                btn.click()
                page.wait_for_timeout(500)  # type: ignore[union-attr]
                return
        except Exception:
            continue
