"""Parse LinkedIn job search HTML (guest + logged-in SPA cards)."""

from __future__ import annotations

import re

from agentzero.models import RawRecord

LINKEDIN_BASE = "https://www.linkedin.com"

_JOB_MARKERS = (
    "base-search-card",
    "jobs-search-results-list",
    "jobs-search__results-list",
    "job-search-card",
    "scm-job-card",
    "jobs-search-results__list-item",
    "job-card-container",
    "job-card-list",
    'aria-label="Dismiss ',
    "Easy Apply",
    "Actively reviewing applicants",
    "jobPosting:",
)

_CAPTCHA_MARKERS = (
    "captcha",
    "challenge",
    "verify you are human",
    "unusual activity",
)

_LOGIN_URL_MARKERS = (
    "authwall",
    "checkpoint",
    "login",
)

_LOGIN_HTML_MARKERS = (
    "sign in",
    "join linkedin",
    'name="session_key"',
)

_DISMISS_LABEL_RE = re.compile(r"^Dismiss (.+) job$")
_JOB_VIEW_URL_RE = re.compile(
    r"(?:https?://(?:www\.)?linkedin\.com)?(/jobs/view/[^\s\"'<>\\]+)",
    re.IGNORECASE,
)
_JOB_POSTING_URN_RE = re.compile(r"jobPosting:(\d{6,})")
_JOB_ID_FROM_URL_RE = re.compile(r"/jobs/view/(?:[\w-]+-)?(\d{6,})/?$")
_JSON_STRING_RE = r'"(?:\\.|[^"\\])*"'
_LOCATION_RE = re.compile(
    r"\bremote\b|,\s*[A-Z]{2}\b|^United States\b|^Canada\b",
    re.IGNORECASE,
)
_SALARY_RE = re.compile(r"\$\s*[\d,]+(?:\.\d+)?\s*[kK]?\s*/?\s*yr", re.IGNORECASE)
_SKIP_TEXT_RE = re.compile(
    r"^(?:·|\s*•\s*|easy apply|posted\b|actively reviewing|medical,|\d+\s+days?\s+ago)",
    re.IGNORECASE,
)
_EMBEDDED_SALARY_PATTERNS = (
    re.compile(r'"formattedSalary"\s*:\s*(' + _JSON_STRING_RE + r")"),
    re.compile(r'"salaryDescription"\s*:\s*(' + _JSON_STRING_RE + r")"),
    re.compile(r'"compensationText"\s*:\s*(' + _JSON_STRING_RE + r")"),
    re.compile(r'"totalSalary"\s*:\s*(' + _JSON_STRING_RE + r")"),
)
_EMBEDDED_COMPANY_PATTERNS = (
    re.compile(r'"companyName"\s*:\s*(' + _JSON_STRING_RE + r")"),
    re.compile(r'"company"\s*:\s*\{\s*"name"\s*:\s*(' + _JSON_STRING_RE + r")"),
    re.compile(
        r'"companyResolutionResult"\s*:\s*\{\s*[^}]*"name"\s*:\s*(' + _JSON_STRING_RE + r")"
    ),
    re.compile(r'"subtitle"\s*:\s*(' + _JSON_STRING_RE + r")"),
    re.compile(
        r'"primaryDescription"\s*:\s*\{\s*"text"\s*:\s*(' + _JSON_STRING_RE + r")"
    ),
    re.compile(r'"companyDetails"\s*:\s*\{\s*"company"\s*:\s*(' + _JSON_STRING_RE + r")"),
)


def page_has_job_results(html: str) -> bool:
    return any(marker in html for marker in _JOB_MARKERS)


def page_session_ready(html: str, url: str = "") -> bool:
    if page_has_job_results(html):
        return True
    url_lower = url.lower()
    if "/feed/" in url_lower or "/in/" in url_lower:
        return True
    return False


def page_needs_login(html: str, url: str = "") -> bool:
    if page_session_ready(html, url):
        return False
    url_lower = url.lower()
    if any(token in url_lower for token in _LOGIN_URL_MARKERS):
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


def build_linkedin_search_url(*, term: str, parsed: object) -> str:
    from urllib.parse import quote_plus

    from agentzero.scrape.location import ParsedLocation

    assert isinstance(parsed, ParsedLocation)
    params = [
        f"keywords={quote_plus(term)}",
        f"location={quote_plus(parsed.jobspy_location)}",
    ]
    if parsed.is_remote:
        params.append("f_WT=2")
    return f"{LINKEDIN_BASE}/jobs/search/?{'&'.join(params)}"


def parse_linkedin_search_html(html: str, *, source: str = "linkedin") -> list[RawRecord]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ImportError("LinkedIn parsing requires beautifulsoup4.") from exc

    soup = BeautifulSoup(html, "html.parser")
    merged: dict[str, RawRecord] = {}

    for record in (
        *_parse_linkedin_legacy_cards(soup, source=source),
        *_parse_linkedin_spa_cards(soup, html, source=source),
        *_parse_linkedin_embedded_jobs(html, source=source),
    ):
        key = _record_dedupe_key(record)
        if key in merged:
            merged[key] = _merge_record(merged[key], record)
        else:
            merged[key] = record

    records: list[RawRecord] = []
    for record in merged.values():
        enriched = _fill_record_gaps(html, soup, record)
        records.append(canonicalize_linkedin_record(enriched))
    return records


def _record_dedupe_key(record: RawRecord) -> str:
    job_id = _job_id_from_url(str(record.get("url") or ""))
    if job_id:
        return job_id
    return "|".join(
        str(record.get(field, "")).strip().lower()
        for field in ("title", "company", "url")
    )


def linkedin_numeric_job_id(url: str) -> str | None:
    """LinkedIn posting id from ``/jobs/view/…`` URLs (slug or numeric path)."""
    match = _JOB_ID_FROM_URL_RE.search(url.rstrip("/"))
    return match.group(1) if match else None


def _job_id_from_url(url: str) -> str | None:
    return linkedin_numeric_job_id(url)


def canonical_linkedin_job_url(url: str) -> str | None:
    """Stable view URL for dedupe/upsert (numeric id path only)."""
    job_id = linkedin_numeric_job_id(url)
    if job_id:
        return f"{LINKEDIN_BASE}/jobs/view/{job_id}"
    return None


def canonicalize_linkedin_record(record: RawRecord) -> RawRecord:
    """Normalize ``url`` so the same posting does not get multiple stable ids."""
    canonical = canonical_linkedin_job_url(str(record.get("url") or ""))
    if not canonical:
        return record
    out = dict(record)
    out["url"] = canonical
    return out


def _merge_record(existing: RawRecord, new: RawRecord) -> RawRecord:
    merged = dict(existing)
    for field in ("title", "company", "url", "source", "location", "comp_raw", "remote"):
        if field not in new:
            continue
        current = merged.get(field)
        incoming = new.get(field)
        if field == "company":
            if _company_is_known(incoming) and not _company_is_known(current):
                merged[field] = incoming
        elif field in {"location", "comp_raw"}:
            if incoming and not current:
                merged[field] = incoming
        elif field == "remote" and incoming is True:
            merged[field] = True
        elif not current and incoming:
            merged[field] = incoming
    return merged  # type: ignore[return-value]


def _company_is_known(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.lower() != "unknown"


def _normalize_job_url(href: str) -> str | None:
    cleaned = href.split("?")[0].strip()
    if not cleaned or "/jobs/view/" not in cleaned:
        return None
    if cleaned.startswith("http"):
        return cleaned
    if cleaned.startswith("/"):
        return f"{LINKEDIN_BASE}{cleaned}"
    return None


def _parse_linkedin_legacy_cards(soup: object, *, source: str) -> list[RawRecord]:
    records: list[RawRecord] = []
    cards = soup.select(  # type: ignore[union-attr]
        "div.base-search-card, li.jobs-search-results__list-item, div.job-search-card"
    )
    for card in cards:
        link = card.select_one("a.base-card__full-link") or card.find("a", href=True)
        if link is None:
            continue
        url = _normalize_job_url(link.get("href", ""))
        if not url:
            continue

        title_el = card.select_one("span.sr-only") or card.select_one("h3")
        title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
        if not title:
            continue

        company_el = card.select_one("h4.base-search-card__subtitle") or card.select_one(
            "a.hidden-nested-link"
        )
        company = (
            company_el.get_text(strip=True)
            if company_el
            else (_company_from_card(card) or "Unknown")
        )
        location_el = card.select_one("span.job-search-card__location")
        location = location_el.get_text(strip=True) if location_el else None
        records.append(
            _build_record(
                title=title,
                company=company,
                url=url,
                source=source,
                location=location,
            )
        )
    return records


def _parse_linkedin_spa_cards(soup: object, html: str, *, source: str) -> list[RawRecord]:
    records: list[RawRecord] = []
    buttons = soup.select('button[aria-label^="Dismiss "][aria-label$=" job"]')  # type: ignore[union-attr]
    for button in buttons:
        label = button.get("aria-label", "")
        match = _DISMISS_LABEL_RE.match(label.strip())
        if not match:
            continue
        title = match.group(1).strip()
        if not title:
            continue

        card = _spa_card_root(button)
        if card is None:
            continue

        company, location, comp_raw = _infer_spa_card_fields(card, title=title)
        url = _find_job_url_for_card(card, html=html, title=title)
        if not url:
            continue

        record = _build_record(
            title=title,
            company=company,
            url=url,
            source=source,
            location=location,
        )
        if comp_raw:
            record["comp_raw"] = comp_raw
        card_text = card.get_text(" ", strip=True)  # type: ignore[union-attr]
        from agentzero.scrape.apply_links import card_signals_easy_apply, safe_http_url

        if card_signals_easy_apply(card_text):
            record["easy_apply"] = True
        for link in card.find_all("a", href=True):  # type: ignore[union-attr]
            href = str(link.get("href") or "")
            if "linkedin.com/jobs/view" in href:
                continue
            if "apply" in href.lower() or "apply" in link.get_text(" ", strip=True).lower():
                external = safe_http_url(href, base_url=url)
                if external:
                    record["apply_url"] = external
                    break
        records.append(record)
    return records


def _spa_card_root(button: object) -> object | None:
    node = button
    best = getattr(button, "parent", None)
    for _ in range(10):
        parent = getattr(node, "parent", None)
        if parent is None or getattr(parent, "name", None) in {"body", "html", "[document]"}:
            break
        node = parent
        if node.select('a[href*="/jobs/view/"]'):  # type: ignore[union-attr]
            return node
        if node.select('div[role="button"]'):  # type: ignore[union-attr]
            best = node
    return best


def _clean_company_name(text: str) -> str:
    cleaned = text.strip()
    if cleaned.lower().endswith(" logo"):
        cleaned = cleaned[:-5].strip()
    return cleaned


def _company_from_card(card: object) -> str | None:
    link = card.select_one('a[href*="/company/"]')  # type: ignore[union-attr]
    if link is not None:
        text = _clean_company_name(link.get_text(strip=True))
        if text:
            return text

    logo = card.select_one('img[src*="company-logo"], img[alt][src*="licdn.com"]')  # type: ignore[union-attr]
    if logo is not None:
        alt = _clean_company_name(str(logo.get("alt") or ""))
        if alt and alt.lower() not in {"logo", "company logo"}:
            return alt

    return None


def _infer_spa_card_fields(
    card: object,
    *,
    title: str,
) -> tuple[str, str | None, str | None]:
    company = _company_from_card(card)
    location: str | None = None
    comp_raw: str | None = None

    for element in card.find_all("p"):  # type: ignore[union-attr]
        text = element.get_text(" ", strip=True)
        if not text or text == title:
            continue
        if _SKIP_TEXT_RE.search(text):
            continue
        if _SALARY_RE.search(text):
            comp_raw = text
            continue
        if location is None and _LOCATION_RE.search(text):
            location = text
            continue
        if company is None and len(text) <= 80 and "$" not in text:
            company = text

    if company is None:
        for element in card.select('div[role="button"] span, div[role="button"] p'):  # type: ignore[union-attr]
            text = element.get_text(" ", strip=True)
            if not text or text == title:
                continue
            if _SKIP_TEXT_RE.search(text) or _SALARY_RE.search(text):
                continue
            if _LOCATION_RE.search(text):
                if location is None:
                    location = text
                continue
            if len(text) <= 80 and "$" not in text:
                company = text
                break

    return company or "Unknown", location, comp_raw


def _find_job_url_for_card(card: object, *, html: str, title: str) -> str | None:
    for link in card.find_all("a", href=True):  # type: ignore[union-attr]
        url = _normalize_job_url(link.get("href", ""))
        if url:
            return url

    role_card = card.select_one('div[role="button"]')  # type: ignore[union-attr]
    if role_card is not None:
        anchor = str(role_card.get("componentkey") or "")
    else:
        anchor = str(card.get("componentkey") or "")  # type: ignore[union-attr]
    if not anchor:
        anchor = title
    return _find_nearby_job_url(html, anchor=anchor, title=title)


def _find_nearby_job_url(html: str, *, anchor: str, title: str) -> str | None:
    for needle in (anchor, title):
        if not needle:
            continue
        pos = html.find(needle)
        if pos == -1:
            continue
        chunk_start = max(0, pos - 6000)
        chunk = html[chunk_start : pos + 6000]
        anchor_pos = pos - chunk_start

        job_id = _closest_job_posting_id(chunk, anchor_pos=anchor_pos)
        if job_id:
            return f"{LINKEDIN_BASE}/jobs/view/{job_id}"

        url = _closest_job_view_url(chunk, anchor_pos=anchor_pos)
        if url:
            return url
    return None


def _closest_job_posting_id(chunk: str, *, anchor_pos: int) -> str | None:
    best_id: str | None = None
    best_dist = 10**9
    for match in _JOB_POSTING_URN_RE.finditer(chunk):
        dist = abs(match.start() - anchor_pos)
        if dist < best_dist:
            best_dist = dist
            best_id = match.group(1)
    return best_id


def _closest_job_view_url(chunk: str, *, anchor_pos: int) -> str | None:
    best_url: str | None = None
    best_dist = 10**9
    for match in _JOB_VIEW_URL_RE.finditer(chunk):
        url = _normalize_job_url(match.group(1))
        if not url:
            continue
        dist = abs(match.start() - anchor_pos)
        if dist < best_dist:
            best_dist = dist
            best_url = url
    return best_url


def _parse_linkedin_embedded_jobs(html: str, *, source: str) -> list[RawRecord]:
    records: list[RawRecord] = []
    seen_ids: set[str] = set()
    for job_id in _JOB_POSTING_URN_RE.findall(html):
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)
        title, company, location, comp_raw = _embedded_job_fields(html, job_id=job_id)
        if not title:
            continue
        record = _build_record(
            title=title,
            company=company or "Unknown",
            url=f"{LINKEDIN_BASE}/jobs/view/{job_id}",
            source=source,
            location=location,
            comp_raw=comp_raw,
        )
        records.append(record)
    return records


def _embedded_job_fields(
    html: str,
    *,
    job_id: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    chunk = _job_object_chunk(html, job_id=job_id)
    if not chunk:
        return None, None, None, None
    title_match = re.search(r'"title"\s*:\s*(' + _JSON_STRING_RE + r")", chunk)
    if not title_match:
        return None, None, None, None
    title = _unescape_json(title_match.group(1).strip('"')).strip()
    company = _embedded_company_from_chunk(chunk, title=title)
    location = _embedded_location_from_chunk(chunk)
    comp_raw = _embedded_salary_from_chunk(chunk) or _salary_from_html_vicinity(
        html, job_id=job_id
    )
    return title or None, company, location, comp_raw


def _job_object_chunk(html: str, *, job_id: str) -> str | None:
    """Extract the JSON object for one job posting from inline Voyager payloads."""
    needle = f"jobPosting:{job_id}"
    pos = html.find(needle)
    if pos == -1:
        return None
    start = html.rfind("{", max(0, pos - 1200), pos + 1)
    if start == -1:
        return None
    depth = 0
    end = start
    for idx in range(start, min(len(html), start + 4000)):
        ch = html[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    if end <= start:
        return None
    return html[start:end]


def _embedded_company_from_chunk(chunk: str, *, title: str) -> str | None:
    for pattern in _EMBEDDED_COMPANY_PATTERNS:
        match = pattern.search(chunk)
        if match is None:
            continue
        company = _normalize_company_candidate(match.group(1).strip('"'), title=title)
        if company:
            return company
    return None


def _embedded_salary_from_chunk(chunk: str) -> str | None:
    for pattern in _EMBEDDED_SALARY_PATTERNS:
        match = pattern.search(chunk)
        if match is None:
            continue
        text = _unescape_json(match.group(1).strip('"')).strip()
        if text and _SALARY_RE.search(text):
            return text
    salary_match = _SALARY_RE.search(chunk)
    if salary_match:
        return salary_match.group(0).strip()
    return None


def _salary_from_html_vicinity(html: str, *, job_id: str) -> str | None:
    needles = (f"jobPosting:{job_id}", f"/jobs/view/{job_id}")
    for needle in needles:
        pos = html.find(needle)
        if pos == -1:
            continue
        chunk = html[max(0, pos - 5000) : pos + 5000]
        salary_match = _SALARY_RE.search(chunk)
        if salary_match:
            return salary_match.group(0).strip()
    return None


def _embedded_location_from_chunk(chunk: str) -> str | None:
    match = re.search(r'"formattedLocation"\s*:\s*(' + _JSON_STRING_RE + r")", chunk)
    if not match:
        return None
    location = _unescape_json(match.group(1).strip('"')).strip()
    return location or None


def _normalize_company_candidate(raw: str, *, title: str) -> str | None:
    text = _clean_company_name(_unescape_json(raw))
    if not text or text.casefold() == title.casefold():
        return None
    if "·" in text:
        text = text.split("·", 1)[0].strip()
    if " • " in text:
        text = text.split(" • ", 1)[0].strip()
    if _SKIP_TEXT_RE.search(text) or _SALARY_RE.search(text):
        return None
    if _LOCATION_RE.search(text) and "," in text and not text.lower().startswith("united states"):
        return None
    if len(text) > 80:
        return None
    return text or None


def _company_from_html_vicinity(html: str, *, job_id: str) -> str | None:
    needles = (f"jobPosting:{job_id}", f"/jobs/view/{job_id}")
    for needle in needles:
        pos = html.find(needle)
        if pos == -1:
            continue
        chunk = html[max(0, pos - 5000) : pos + 5000]
        link_match = re.search(
            r'href="(?:https://www\.linkedin\.com)?/company/[^"]+"[^>]*>\s*([^<]+?)\s*<',
            chunk,
            re.IGNORECASE,
        )
        if link_match:
            company = link_match.group(1).strip()
            if company:
                return company
    return None


def _fill_record_gaps(html: str, soup: object, record: RawRecord) -> RawRecord:
    job_id = _job_id_from_url(str(record.get("url") or ""))
    if not job_id:
        return record

    title = str(record.get("title") or "")
    embedded = _embedded_job_fields(html, job_id=job_id)
    updated = dict(record)

    if not _company_is_known(record.get("company")):
        company = embedded[1]
        if not company:
            company = _company_from_html_vicinity(html, job_id=job_id)
        if not company:
            company = _company_from_title_vicinity(soup, html, title=title, job_id=job_id)
        if company:
            updated["company"] = company

    if not record.get("comp_raw"):
        comp_raw = embedded[3] or _salary_from_html_vicinity(html, job_id=job_id)
        if comp_raw:
            updated["comp_raw"] = comp_raw

    if updated == dict(record):
        return record
    return updated  # type: ignore[return-value]


def _company_from_title_vicinity(
    soup: object,
    html: str,
    *,
    title: str,
    job_id: str,
) -> str | None:
    pos = html.find(title)
    if pos == -1:
        pos = html.find(f"jobPosting:{job_id}")
    if pos == -1:
        return None

    chunk_html = html[max(0, pos - 5000) : pos + 5000]
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    chunk_soup = BeautifulSoup(chunk_html, "html.parser")
    company = _company_from_card(chunk_soup)
    if company:
        return company

    for element in chunk_soup.find_all("p"):
        text = element.get_text(" ", strip=True)
        if not text or text == title:
            continue
        if _SKIP_TEXT_RE.search(text) or _SALARY_RE.search(text):
            continue
        if _LOCATION_RE.search(text):
            continue
        if len(text) <= 80 and "$" not in text:
            return text
    return None


def _unescape_json(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("\\u0026", "&").replace('\\"', '"').replace("\\\\", "\\")


def _build_record(
    *,
    title: str,
    company: str,
    url: str,
    source: str,
    location: str | None = None,
    comp_raw: str | None = None,
) -> RawRecord:
    record: RawRecord = {
        "title": title,
        "company": company,
        "url": url,
        "source": source,
    }
    if location:
        record["location"] = location
        if "remote" in location.lower():
            record["remote"] = True
    if comp_raw:
        record["comp_raw"] = comp_raw
    return record
