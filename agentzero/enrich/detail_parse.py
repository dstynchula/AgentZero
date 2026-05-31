"""Parse job detail pages for description, salary, and company hints."""

from __future__ import annotations

import json
import re
from typing import Any

from agentzero.scrape.validate import parse_comp_from_text

DESCRIPTION_SELECTORS = (
    "div.show-more-less-html__markup",
    "div.description__text",
    "div#job-details",
    "div.jobs-description__content",
    "div.jobsearch-JobComponent-description",
    "div[data-testid='job-description']",
)


def _text_from_soup(soup: object, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        el = soup.select_one(selector)  # type: ignore[union-attr]
        if el is not None:
            text = el.get_text("\n", strip=True)
            if len(text) > 80:
                return text
    return None


def _json_ld_description(html: str) -> str | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            desc = item.get("description")
            if isinstance(desc, str) and len(desc) > 80:
                return desc
    return None


LINKEDIN_SALARY_SELECTORS = (
    "div.job-details-jobs-unified-top-card__job-insight span",
    "div.jobs-unified-top-card__job-insight span",
    "span.job-details-jobs-unified-top-card__job-insight-view-model-secondary",
    "div.salary-main-rail__data-body",
    "div.compensation__salary",
)


def parse_linkedin_job_detail_html(html: str) -> dict[str, Any]:
    """Extract fields from a LinkedIn job view page."""
    out: dict[str, Any] = {}
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return out

    soup = BeautifulSoup(html, "html.parser")
    desc = _text_from_soup(soup, DESCRIPTION_SELECTORS) or _json_ld_description(html)
    if desc:
        out["description"] = desc

    salary_text = _text_from_soup(soup, LINKEDIN_SALARY_SELECTORS)
    if not salary_text:
        for insight in soup.select(
            "div.job-details-jobs-unified-top-card__job-insight, "
            "li.job-details-jobs-unified-top-card__job-insight"
        ):
            text = insight.get_text(" ", strip=True)
            if "$" in text and ("yr" in text.lower() or "year" in text.lower() or "/hr" in text.lower()):
                salary_text = text
                break

    if salary_text:
        low, high, currency = parse_comp_from_text(salary_text)
        if low is not None or high is not None:
            out["comp_min"] = low
            out["comp_max"] = high
            if currency:
                out["currency"] = currency

    page_text = soup.get_text(" ", strip=True)
    if "comp_min" not in out and "comp_max" not in out:
        low, high, currency = parse_comp_from_text(page_text)
        if low is not None or high is not None:
            out["comp_min"] = low
            out["comp_max"] = high
            if currency:
                out["currency"] = currency

    emp = re.search(r"([\d,]+)\+?\s+employees", page_text, re.I)
    if emp:
        raw_count = emp.group(1).replace(",", "").strip()
        if raw_count.isdigit():
            out["company_size_hint"] = int(raw_count)

    return out


def parse_indeed_job_detail_html(html: str) -> dict[str, Any]:
    """Extract fields from an Indeed viewjob page."""
    out: dict[str, Any] = {}
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return out

    soup = BeautifulSoup(html, "html.parser")
    desc = _text_from_soup(soup, DESCRIPTION_SELECTORS) or _json_ld_description(html)
    if desc:
        out["description"] = desc

    salary_el = soup.select_one("#salaryInfoAndJobType, .jobsearch-JobMetadataHeader-item")
    if salary_el:
        low, high, currency = parse_comp_from_text(salary_el.get_text(" ", strip=True))
        if low is not None or high is not None:
            out["comp_min"] = low
            out["comp_max"] = high
            if currency:
                out["currency"] = currency

    return out


def parse_glassdoor_job_detail_html(html: str, *, title: str = "", url: str = "") -> dict[str, Any]:
    """Extract fields from a Glassdoor job view page."""
    from agentzero.scrape.glassdoor_company import company_from_glassdoor_html

    out: dict[str, Any] = {}
    company = company_from_glassdoor_html(html, title=title, url=url)
    if company:
        out["company"] = company

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return out

    soup = BeautifulSoup(html, "html.parser")
    desc = _text_from_soup(soup, DESCRIPTION_SELECTORS) or _json_ld_description(html)
    if desc:
        out["description"] = desc
        if not company:
            from agentzero.scrape.glassdoor_company import company_from_glassdoor_description

            resolved = company_from_glassdoor_description(desc, title=title)
            if resolved:
                out["company"] = resolved

    salary_el = soup.select_one('[data-test="detailSalary"], .salaryEstimate')
    if salary_el:
        low, high, currency = parse_comp_from_text(salary_el.get_text(" ", strip=True))
        if low is not None or high is not None:
            out["comp_min"] = low
            out["comp_max"] = high
            if currency:
                out["currency"] = currency

    return out


def parse_job_detail_html(html: str, *, source: str, title: str = "", url: str = "") -> dict[str, Any]:
    key = source.lower().replace("_browser", "")
    if "glassdoor" in key:
        return parse_glassdoor_job_detail_html(html, title=title, url=url)
    if "linkedin" in key:
        return parse_linkedin_job_detail_html(html)
    if "indeed" in key:
        return parse_indeed_job_detail_html(html)
    desc = _json_ld_description(html)
    return {"description": desc} if desc else {}
