"""Parallel + sequential enrichment batch runner with progress output."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentzero.enrich.company_research import CompanyFactsCache
from agentzero.enrich.gaps import enrichment_gaps, needs_detail_fetch
from agentzero.enrich.pipeline import enrich_job, enrich_job_deep
from agentzero.loops.progress import Progress
from agentzero.loops.ralph import run_parallel
from agentzero.models import JobPosting

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.storage.db import Database

log = logging.getLogger(__name__)


def _job_enrich_status(job: JobPosting) -> str:
    gaps = enrichment_gaps(job)
    if gaps:
        return f"{job.title} @ {job.company} -> still missing: {', '.join(gaps)}"
    bits: list[str] = []
    if job.comp_min or job.comp_max:
        bits.append("comp")
    if job.company_size:
        bits.append("size")
    if job.glassdoor_rating is not None:
        bits.append(f"GD {job.glassdoor_rating}")
    if job.careers_url:
        bits.append("careers")
    if job.description:
        bits.append("description")
    return f"{job.title} @ {job.company} -> {', '.join(bits) or 'ok'}"


def enrichment_summary(job: JobPosting, *, before: list[str]) -> str:
    """One-line status for progress output."""
    after = enrichment_gaps(job)
    filled: list[str] = []
    if "comp" in before and "comp" not in after and (job.comp_min or job.comp_max):
        lo = f"${job.comp_min:,.0f}" if job.comp_min else "?"
        hi = f"${job.comp_max:,.0f}" if job.comp_max else "?"
        filled.append(f"comp {lo}-{hi}")
    if "company_size" in before and job.company_size:
        filled.append(f"size {job.company_size}")
    if "glassdoor_rating" in before and job.glassdoor_rating is not None:
        filled.append(f"GD {job.glassdoor_rating}")
    if "careers_url" in before and job.careers_url and "careers_url" not in after:
        filled.append("careers")
    if "description" in before and job.description and "description" not in after:
        filled.append("description")
    if filled:
        return "filled: " + ", ".join(filled)
    if after:
        return "still missing: " + ", ".join(after)
    return "complete"


@dataclass
class EnrichBatchResult:
    improved: int
    total: int
    failed: int


def run_enrich_batch(
    db: Database,
    job_ids: list[str],
    *,
    settings: Settings,
    max_workers: int,
    fetch_detail: bool,
    glassdoor_lookup: bool,
    web_search: bool,
    allow_browser: bool,
    browser_delay_seconds: float,
) -> EnrichBatchResult:
    """Parallel HTTP + Glassdoor, then sequential browser fallback for stragglers."""
    if not job_ids:
        return EnrichBatchResult(improved=0, total=0, failed=0)

    improved = 0
    failed = 0
    improve_lock = threading.Lock()
    print(
        f"Enrich plan: {max_workers} parallel worker(s), "
        f"HTTP detail={'on' if fetch_detail else 'off'}, "
        f"browser={'on' if allow_browser and fetch_detail else 'off'}, "
        f"glassdoor={'on' if glassdoor_lookup else 'off'}, "
        f"web_search={'on' if web_search and settings.enrich_web_search else 'off'}",
        flush=True,
    )

    company_cache = CompanyFactsCache()
    parallel_progress = Progress(len(job_ids), label="Enrich")
    parallel_progress.announce("HTTP detail + parse + Glassdoor + web search")

    def parallel_worker(job_id: str) -> None:
        nonlocal failed
        job = db.get_job(job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        before = enrichment_gaps(job)
        try:
            updated = enrich_job_deep(
                job,
                settings=settings,
                fetch_detail=fetch_detail,
                glassdoor_lookup=glassdoor_lookup,
                web_search=web_search,
                allow_browser=False,
                company_cache=company_cache,
            )
        except Exception:
            log.exception("Parallel enrich failed for %s", job_id)
            db.mark_pipeline(job_id, "enrich_status", "failed")
            with improve_lock:
                failed += 1
            return
        db.upsert_job(updated)
        db.mark_pipeline(job_id, "enrich_status", "done")
        if len(enrichment_gaps(updated)) < len(before):
            with improve_lock:
                nonlocal improved
                improved += 1

    def parallel_label(job_id: str) -> str:
        job = db.get_job(job_id)
        return _job_enrich_status(job) if job else job_id

    failures = run_parallel(
        job_ids,
        parallel_worker,
        max_workers=max_workers,
        progress=parallel_progress,
        item_label=parallel_label,
    )
    failed += len(failures)
    parallel_progress.finish()

    if not allow_browser or not fetch_detail:
        return EnrichBatchResult(improved=improved, total=len(job_ids), failed=failed)

    browser_ids = [
        jid
        for jid in job_ids
        if (job := db.get_job(jid)) is not None and needs_detail_fetch(job)
    ]
    if not browser_ids:
        return EnrichBatchResult(improved=improved, total=len(job_ids), failed=failed)

    print(
        f"\nBrowser detail fallback for {len(browser_ids)} job(s) "
        f"(sequential — avoids profile conflicts)…",
        flush=True,
    )
    browser_progress = Progress(len(browser_ids), label="Browser detail")
    browser_progress.announce()

    for job_id in browser_ids:
        job = db.get_job(job_id)
        if job is None:
            continue
        before = enrichment_gaps(job)
        try:
            updated = enrich_job_deep(
                job,
                settings=settings,
                fetch_detail=True,
                glassdoor_lookup=False,
                web_search=False,
                allow_browser=True,
            )
            updated = enrich_job(updated)
        except Exception:
            log.exception("Browser enrich failed for %s", job_id)
            db.mark_pipeline(job_id, "enrich_status", "failed")
            failed += 1
            browser_progress.step(f"FAILED {job.title} @ {job.company}")
            continue
        db.upsert_job(updated)
        db.mark_pipeline(job_id, "enrich_status", "done")
        browser_progress.step(
            f"{job.title} @ {job.company} -> {enrichment_summary(updated, before=before)}"
        )
        if len(enrichment_gaps(updated)) < len(before):
            improved += 1
        if browser_delay_seconds > 0:
            time.sleep(browser_delay_seconds)

    browser_progress.finish()
    return EnrichBatchResult(improved=improved, total=len(job_ids), failed=failed)
