"""Fetch job detail pages to fill description and inline salary hints."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from agentzero.enrich.detail_parse import parse_job_detail_html
from agentzero.models import JobPosting
from agentzero.net.http_client import safe_get_text
from agentzero.net.url_safety import UnsafeURLError, url_host_matches, validate_fetch_url
from agentzero.scrape.resilience import DEFAULT_USER_AGENT

if TYPE_CHECKING:
    from agentzero.config import Settings

log = logging.getLogger(__name__)


def _fetch_html_http(url: str, *, user_agent: str, timeout: float) -> str | None:
    return safe_get_text(url, user_agent=user_agent, timeout=timeout)


def _browser_site_for_job(job: JobPosting) -> str | None:
    if url_host_matches(job.url, "linkedin.com"):
        return "linkedin"
    if url_host_matches(job.url, "indeed.com"):
        return "indeed"
    if url_host_matches(job.url, "glassdoor.com"):
        return "glassdoor"
    return None


def _fetch_html_browser(url: str, *, settings: Settings, site: str) -> str | None:
    try:
        validate_fetch_url(url)
    except UnsafeURLError as exc:
        log.warning("Blocked unsafe browser detail URL %s: %s", url, exc)
        return None
    from agentzero.scrape.browser_common import launch_browser_page

    playwright = context = None
    try:
        playwright, context, page = launch_browser_page(
            settings,
            site=site,
            headless=settings.scrape_browser_headless,
        )
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            validate_fetch_url(page.url)
        except UnsafeURLError as exc:
            log.warning("Browser landed on unsafe URL %s: %s", page.url, exc)
            return None
        page.wait_for_timeout(2_000)
        return page.content()
    except Exception as exc:
        log.warning("Browser detail fetch failed for %s: %s", url, exc)
        return None
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()


def fetch_job_detail_html(
    job: JobPosting,
    *,
    settings: Settings,
    allow_browser: bool = True,
) -> str | None:
    """HTTP first, then Playwright with the board's saved profile when allowed."""
    ua = settings.scrape_user_agent or DEFAULT_USER_AGENT
    html = _fetch_html_http(job.url, user_agent=ua, timeout=25.0)
    if html and len(html) > 500:
        return html
    if not allow_browser:
        return html
    site = _browser_site_for_job(job)
    if site is None:
        return html
    return _fetch_html_browser(job.url, settings=settings, site=site)


def fetch_and_merge_detail_http(job: JobPosting, *, settings: Settings) -> JobPosting:
    """Detail fetch via HTTP only (safe for parallel workers)."""
    html = fetch_job_detail_html(job, settings=settings, allow_browser=False)
    if not html:
        return job
    fields = parse_job_detail_html(html, source=job.source, title=job.title, url=job.url)
    return merge_detail_fields(job, fields)


def merge_detail_fields(job: JobPosting, fields: dict[str, Any]) -> JobPosting:
    """Apply parsed detail fields without overwriting existing values."""
    updates: dict[str, Any] = {}
    if fields.get("description") and not job.description:
        updates["description"] = fields["description"]
    company = fields.get("company")
    if company and job.company.strip().lower() in {"", "unknown"}:
        updates["company"] = str(company).strip()
    if job.comp_min is None and job.comp_max is None:
        if fields.get("comp_min") is not None:
            updates["comp_min"] = fields["comp_min"]
        if fields.get("comp_max") is not None:
            updates["comp_max"] = fields["comp_max"]
        if fields.get("currency"):
            updates["currency"] = fields["currency"]
        if updates.get("comp_min") or updates.get("comp_max"):
            updates["comp_is_estimate"] = True
    hint = fields.get("company_size_hint")
    if hint and not job.company_size:
        from agentzero.enrich.company import bucket_employee_count

        updates["company_size"] = bucket_employee_count(int(hint))
    if not updates:
        return job
    return job.model_copy(update=updates)


def fetch_and_merge_detail(
    job: JobPosting,
    *,
    settings: Settings,
    allow_browser: bool = True,
) -> JobPosting:
    html = fetch_job_detail_html(job, settings=settings, allow_browser=allow_browser)
    if not html:
        return job
    fields = parse_job_detail_html(html, source=job.source, title=job.title, url=job.url)
    return merge_detail_fields(job, fields)


def fetch_details_batch(
    jobs: list[JobPosting],
    *,
    settings: Settings,
    delay_seconds: float,
) -> list[JobPosting]:
    updated: list[JobPosting] = []
    for index, job in enumerate(jobs, start=1):
        print(
            f"Detail [{index}/{len(jobs)}] {job.title} @ {job.company}…",
            flush=True,
        )
        merged = fetch_and_merge_detail(job, settings=settings)
        updated.append(merged)
        if delay_seconds > 0 and index < len(jobs):
            time.sleep(delay_seconds)
    return updated
