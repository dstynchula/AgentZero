"""Extract apply / easy-apply URLs from job listing HTML."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from agentzero.net.url_safety import UnsafeURLError, validate_fetch_url

_EASY_APPLY_RE = re.compile(r"easy\s*apply", re.I)
_APPLY_HREF_RE = re.compile(r"apply|application", re.I)


def safe_http_url(url: str | None, *, base_url: str | None = None) -> str | None:
    if not url or not str(url).strip():
        return None
    candidate = str(url).strip()
    if base_url and candidate.startswith("/"):
        candidate = urljoin(base_url, candidate)
    try:
        validate_fetch_url(candidate)
    except UnsafeURLError:
        return None
    return candidate


def extract_apply_fields_from_html(
    html: str,
    *,
    source: str,
    posting_url: str,
) -> dict[str, Any]:
    """Best-effort apply_url, easy_apply_url, and easy_apply flag from a detail page."""
    out: dict[str, Any] = {}
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return out

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    if _EASY_APPLY_RE.search(page_text):
        out["easy_apply"] = True

    posting = safe_http_url(posting_url)
    candidates: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        text = anchor.get_text(" ", strip=True)
        if _APPLY_HREF_RE.search(href) or _APPLY_HREF_RE.search(text):
            resolved = safe_http_url(href, base_url=posting_url)
            if resolved and resolved != posting:
                candidates.append(resolved)

    key = source.lower()
    if "indeed" in key:
        for sel in (
            "a.ia-IndeedApplyButton",
            "a[data-testid='indeedApplyButton']",
            "a[id*='apply']",
        ):
            el = soup.select_one(sel)
            if el and el.get("href"):
                resolved = safe_http_url(str(el["href"]), base_url=posting_url)
                if resolved:
                    candidates.insert(0, resolved)
    elif "linkedin" in key:
        for sel in (
            "a.jobs-apply-button",
            "a[data-control-name='jobdetails_topcard_inapply']",
            "a[href*='externalApply']",
        ):
            el = soup.select_one(sel)
            if el and el.get("href"):
                resolved = safe_http_url(str(el["href"]), base_url=posting_url)
                if resolved:
                    candidates.insert(0, resolved)
    elif "glassdoor" in key:
        el = soup.select_one('a[data-test="applyButton"], a[href*="jobListingId"]')
        if el and el.get("href"):
            resolved = safe_http_url(str(el["href"]), base_url=posting_url)
            if resolved:
                candidates.insert(0, resolved)

    if candidates:
        out["apply_url"] = candidates[0]
        if out.get("easy_apply") and len(candidates) > 1:
            out["easy_apply_url"] = candidates[1]
        elif out.get("easy_apply") and candidates[0] != posting:
            out["easy_apply_url"] = candidates[0]

    return out


def card_signals_easy_apply(card_text: str) -> bool:
    return bool(_EASY_APPLY_RE.search(card_text))
