"""End-to-end scrape -> validate -> enrich -> rank pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentzero.enrich.pipeline import enrich_job
from agentzero.loops.ralph import run_parallel
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.rank.matcher import rank_job
from agentzero.scrape.comp_filter import filter_by_salary_floor
from agentzero.scrape.title_filter import filter_by_title_relevance
from agentzero.scrape.validate import assert_source_healthy, validate_batch

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.ingest.resume import ResumeProfile
    from agentzero.llm.provider import LLMProvider
    from agentzero.scrape.base import JobSource
    from agentzero.storage.db import Database


@dataclass
class PipelineResult:
    scraped: int = 0
    quarantined: int = 0
    enriched: int = 0
    ranked: int = 0
    comp_filtered: int = 0
    title_filtered: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class Pipeline:
    def __init__(
        self,
        db: Database,
        source: JobSource,
        *,
        settings: Settings | None = None,
        llm: LLMProvider | None = None,
        max_workers: int = 4,
    ) -> None:
        self._db = db
        self._source = source
        self._run_settings = settings
        self._llm = llm
        self._max_workers = max_workers

    def run(
        self,
        *,
        profile: ResumeProfile | None = None,
        new_status: ApplicationStatus = ApplicationStatus.NEW,
    ) -> PipelineResult:
        result = PipelineResult()
        from agentzero.config import get_settings

        cfg = self._run_settings or get_settings()
        print("Scraping job boards (may take several minutes)…", flush=True)
        raw_records = list(self._source.fetch())
        print(f"Fetched {len(raw_records)} raw listing(s). Validating…", flush=True)
        jobs, quarantined, metrics = validate_batch(
            raw_records, source=self._source.name, llm=self._llm
        )

        source_healthy = True
        try:
            assert_source_healthy(metrics)
        except RuntimeError as exc:
            msg = str(exc)
            result.errors.append(msg)
            source_healthy = False
            print(f"\nWARNING: {msg}", flush=True)
            print("Skipping job upserts for this run.", flush=True)

        for raw, error in quarantined:
            self._db.add_quarantine(raw_payload=raw, error=error, source=self._source.name)
        result.quarantined = len(quarantined)

        if source_healthy:
            from agentzero.scrape.remote_policy import job_is_remote

            if cfg.remote_only:
                from agentzero.scrape.remote_policy import format_remote_filter_skips

                remote_rejected = [job for job in jobs if not job_is_remote(job)]
                jobs = [job for job in jobs if job_is_remote(job)]
                if remote_rejected:
                    print(
                        f"Remote filter: skipped {len(remote_rejected)} non-remote listing(s).",
                        flush=True,
                    )
                    for line in format_remote_filter_skips(remote_rejected):
                        print(line, flush=True)

            title_kept, title_rejected = filter_by_title_relevance(jobs, cfg.search_terms)
            jobs = title_kept
            result.title_filtered = len(title_rejected)
            if title_rejected:
                print(
                    f"Title filter: skipped {len(title_rejected)} listing(s) "
                    f"not matching {cfg.search_terms!r}.",
                    flush=True,
                )

            salary_floor = cfg.salary_min
            enriched_jobs = [self._enrich_scraped_job(job, cfg) for job in jobs]
            kept, rejected = filter_by_salary_floor(enriched_jobs, salary_floor)
            result.comp_filtered = len(rejected)
            if rejected and salary_floor is not None:
                print(
                    "Comp filter (salary floor configured): "
                    f"skipped {len(rejected)} listing(s) below minimum.",
                    flush=True,
                )

            for job in kept:
                existing = self._db.get_job(job.job_id)
                to_store = self._merge_scrape_job(existing, job, new_status=new_status)
                self._db.upsert_job(to_store)
                self._db.mark_pipeline(job.job_id, "scrape_status", "done")
                self._db.mark_pipeline(job.job_id, "enrich_status", "done")
            result.scraped = len(kept)
            result.enriched = len(kept)

        pending_enrich = self._db.list_pending("enrich_status")
        if pending_enrich:
            print(f"Enriching {len(pending_enrich)} backfill job(s)…", flush=True)
            from agentzero.loops.progress import Progress

            enrich_progress = Progress(len(pending_enrich), label="Enrich")
            enrich_progress.announce()

            def enrich_one(job_id: str) -> None:
                job = self._db.get_job(job_id)
                if job is None:
                    raise KeyError(f"job not found: {job_id}")
                enriched = enrich_job(job)
                self._db.upsert_job(enriched)
                self._db.mark_pipeline(job_id, "enrich_status", "done")

            def enrich_label(job_id: str) -> str:
                job = self._db.get_job(job_id)
                if job is None:
                    return job_id
                return f"{job.title} @ {job.company}"

            failures = run_parallel(
                pending_enrich,
                enrich_one,
                max_workers=self._max_workers,
                progress=enrich_progress,
                item_label=enrich_label,
            )
            enrich_progress.finish()
            result.errors.extend(failures)
            result.enriched += len(pending_enrich) - len(failures)

        if profile and self._llm:
            def rank_one(job_id: str) -> None:
                job = self._db.get_job(job_id)
                if job is None:
                    raise KeyError(f"job not found: {job_id}")
                match = rank_job(
                    job,
                    profile,
                    llm=self._llm,
                    max_description_chars=cfg.rank_description_max_chars,
                )
                updated = job.model_copy(
                    update={
                        "match_score": match.match_score,
                        "match_rationale": match.rationale,
                    }
                )
                self._db.upsert_job(updated)
                self._db.mark_pipeline(job_id, "rank_status", "done")

            pending_rank = self._db.list_pending("rank_status")
            if pending_rank:
                from agentzero.loops.progress import Progress

                rank_workers = cfg.rank_max_concurrency
                print(
                    f"Ranking {len(pending_rank)} job(s) vs résumé "
                    f"({rank_workers} parallel LLM workers)…",
                    flush=True,
                )
                rank_progress = Progress(len(pending_rank), label="Rank")
                rank_progress.announce()

                def rank_label(job_id: str) -> str:
                    job = self._db.get_job(job_id)
                    if job is None:
                        return job_id
                    return f"{job.title} @ {job.company}"

                failures = run_parallel(
                    pending_rank,
                    rank_one,
                    max_workers=rank_workers,
                    progress=rank_progress,
                    item_label=rank_label,
                )
                rank_progress.finish()
                result.errors.extend(failures)
                result.ranked = len(pending_rank) - len(failures)

        return result

    def _enrich_scraped_job(self, job: JobPosting, cfg: Settings) -> JobPosting:
        """Parse comp from description; fetch LinkedIn detail page when salary missing."""
        job = enrich_job(job)
        if job.comp_min is not None or job.comp_max is not None:
            return job
        if "linkedin" not in job.source.lower():
            return job
        from agentzero.enrich.detail_fetch import fetch_and_merge_detail

        job = fetch_and_merge_detail(job, settings=cfg, allow_browser=True)
        return enrich_job(job)

    @staticmethod
    def _merge_scrape_job(
        existing: JobPosting | None,
        job: JobPosting,
        *,
        new_status: ApplicationStatus,
    ) -> JobPosting:
        """Preserve tracker fields on re-scrape; tag brand-new rows with *new_status*."""
        if existing is None:
            return job.model_copy(update={"status": new_status})
        tracking = {
            "status": existing.status,
            "date_applied": existing.date_applied,
            "date_first_contacted": existing.date_first_contacted,
            "notes": existing.notes,
        }
        if existing.status == ApplicationStatus.NEW and new_status != ApplicationStatus.NEW:
            tracking["status"] = new_status
        return job.model_copy(update=tracking)
