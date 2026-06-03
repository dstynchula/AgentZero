"""End-to-end scrape -> validate -> enrich -> rank pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentzero.enrich.pipeline import enrich_job
from agentzero.loops.ralph import run_parallel
from agentzero.loops.run_progress import RunProgress, ScrapeLogLevel
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


def _scrape_log(
    progress: RunProgress | None,
    message: str,
    *,
    level: ScrapeLogLevel = "info",
) -> None:
    print(message, flush=True)
    if progress is not None:
        progress.log(level, message)


@dataclass
class PipelineResult:
    scraped: int = 0
    quarantined: int = 0
    enriched: int = 0
    ranked: int = 0
    comp_filtered: int = 0
    title_filtered: int = 0
    skipped_known: int = 0
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
        progress: RunProgress | None = None,
    ) -> PipelineResult:
        result = PipelineResult()
        from agentzero.config import get_settings
        from agentzero.scrape.factory import list_source_names

        cfg = self._run_settings or get_settings()
        inline_detail = cfg.scrape_inline_detail_enrich
        if progress is not None:
            boards = list_source_names(self._source)
            progress.enter_step(
                "scrape.boards",
                phase="scrape",
                label="Scrape job boards",
                total=len(boards),
                done=0,
                next_step_id=f"scrape.{boards[0]}" if boards else "validate.batch",
                next_step_label=boards[0] if boards else "Validate listings",
                extra={"boards": boards},
            )
        _scrape_log(progress, "Scraping job boards (may take several minutes)…")
        raw_records = list(self._source.fetch(progress=progress))
        if progress is not None:
            from agentzero.scrape.multi import MultiSource

            if not isinstance(self._source, MultiSource):
                boards = list_source_names(self._source)
                progress.set_phase(
                    "scrape",
                    total=len(boards),
                    done=len(boards),
                    detail=boards[0] if boards else "",
                )
        if progress is not None:
            progress.enter_step(
                "validate.batch",
                phase="validate",
                label="Validate listings",
                total=1,
                done=0,
                next_step_id="filter.remote",
                next_step_label="Apply filters",
                extra={"raw_count": len(raw_records)},
            )
        _scrape_log(progress, f"Fetched {len(raw_records)} raw listing(s). Validating…")
        jobs, quarantined, metrics = validate_batch(
            raw_records, source=self._source.name, llm=self._llm
        )
        if progress is not None:
            progress.step(detail=f"{len(jobs)} valid")

        source_healthy = True
        try:
            assert_source_healthy(metrics)
        except RuntimeError as exc:
            msg = str(exc)
            result.errors.append(msg)
            source_healthy = False
            _scrape_log(progress, f"WARNING: {msg}", level="warn")
            _scrape_log(progress, "Skipping job upserts for this run.", level="warn")

        for raw, error in quarantined:
            self._db.add_quarantine(raw_payload=raw, error=error, source=self._source.name)
        result.quarantined = len(quarantined)

        if source_healthy:
            known_ids = set(self._db.list_job_ids())
            before_skip = len(jobs)
            jobs = [job for job in jobs if job.job_id not in known_ids]
            result.skipped_known = before_skip - len(jobs)
            if result.skipped_known:
                _scrape_log(
                    progress,
                    f"Skip known: {result.skipped_known} listing(s) already in database.",
                )

            from agentzero.scrape.remote_policy import job_is_remote

            if progress is not None:
                progress.enter_step(
                    "filter.remote",
                    phase="filter",
                    label="Apply remote filter",
                    total=1,
                    done=0,
                    next_step_id="filter.title",
                    next_step_label="Title relevance filter",
                )

            if cfg.remote_only:
                from agentzero.scrape.remote_policy import format_remote_filter_skips

                remote_rejected = [job for job in jobs if not job_is_remote(job)]
                jobs = [job for job in jobs if job_is_remote(job)]
                if remote_rejected:
                    _scrape_log(
                        progress,
                        f"Remote filter: skipped {len(remote_rejected)} non-remote listing(s).",
                    )
                    for line in format_remote_filter_skips(remote_rejected):
                        _scrape_log(progress, line)

            if progress is not None:
                next_filter = (
                    "filter.enrich_comp" if inline_detail else "filter.comp_floor"
                )
                progress.enter_step(
                    "filter.title",
                    phase="filter",
                    label="Title relevance filter",
                    total=1,
                    done=1,
                    next_step_id=next_filter,
                    next_step_label=(
                        "Enrich listings for comp"
                        if inline_detail
                        else "Comp floor filter"
                    ),
                )
            title_kept, title_rejected = filter_by_title_relevance(jobs, cfg.search_terms)
            jobs = title_kept
            result.title_filtered = len(title_rejected)
            if title_rejected:
                _scrape_log(
                    progress,
                    f"Title filter: skipped {len(title_rejected)} listing(s) "
                    f"not matching {cfg.search_terms!r}.",
                )

            salary_floor = cfg.salary_min
            if inline_detail:
                if progress is not None:
                    progress.enter_step(
                        "filter.enrich_comp",
                        phase="filter",
                        label="Enrich listings for comp (may open detail pages)",
                        total=len(jobs),
                        done=0,
                        next_step_id="filter.comp_floor",
                        next_step_label="Comp floor filter",
                        extra={"job_count": len(jobs)},
                    )
                enriched_jobs: list[JobPosting] = []
                for index, job in enumerate(jobs, start=1):
                    try:
                        enriched = self._enrich_scraped_job(job, cfg)
                    except Exception as exc:  # noqa: BLE001
                        _scrape_log(
                            progress,
                            f"Enrich failed (kept listing): {job.title} @ {job.company}: {exc}",
                            level="warn",
                        )
                        enriched = enrich_job(job, settings=cfg)
                    enriched_jobs.append(enriched)
                    if progress is not None:
                        progress.step(
                            detail=f"{job.title} @ {job.company}",
                            done=index,
                        )
                jobs_for_comp = enriched_jobs
            else:
                jobs_for_comp = [enrich_job(job, settings=cfg) for job in jobs]

            if progress is not None:
                progress.enter_step(
                    "filter.comp_floor",
                    phase="filter",
                    label="Comp floor filter",
                    total=1,
                    done=0,
                    next_step_id="persist.upsert",
                    next_step_label="Save leads to database",
                )
            kept, rejected = filter_by_salary_floor(jobs_for_comp, salary_floor)
            result.comp_filtered = len(rejected)
            if rejected and salary_floor is not None:
                _scrape_log(
                    progress,
                    "Comp filter (salary floor configured): "
                    f"skipped {len(rejected)} listing(s) below minimum.",
                )

            if progress is not None:
                progress.enter_step(
                    "persist.upsert",
                    phase="filter",
                    label="Save leads to database",
                    total=len(kept),
                    done=0,
                    next_step_id="rank.batch" if profile and self._llm else "done",
                    next_step_label="Rank vs résumé" if profile and self._llm else "Complete",
                )

            for index, job in enumerate(kept, start=1):
                existing = self._db.get_job(job.job_id)
                to_store = self._merge_scrape_job(existing, job, new_status=new_status)
                self._db.upsert_job(to_store)
                self._db.mark_pipeline(job.job_id, "scrape_status", "done")
                enrich_status = "done" if inline_detail else "pending"
                self._db.mark_pipeline(job.job_id, "enrich_status", enrich_status)
                if progress is not None:
                    progress.step(
                        detail=f"{job.title} @ {job.company}",
                        done=index,
                    )

            result.scraped = len(kept)
            result.enriched = len(kept) if inline_detail else 0
            if progress is not None and len(kept):
                progress.step(detail=f"{len(kept)} saved")

        if inline_detail:
            pending_enrich = self._db.list_pending("enrich_status")
            if pending_enrich:
                _scrape_log(progress, f"Enriching {len(pending_enrich)} backfill job(s)…")
                if progress is not None:
                    from agentzero.loops.run_progress import RunProgressAdapter

                    enrich_progress = RunProgressAdapter(
                        len(pending_enrich),
                        label="Enrich backfill",
                        run_progress=progress,
                        phase="enrich",
                        step_id="enrich.backfill",
                    )
                else:
                    from agentzero.loops.progress import Progress

                    enrich_progress = Progress(len(pending_enrich), label="Enrich")
                enrich_progress.announce()

                def enrich_one(job_id: str) -> None:
                    job = self._db.get_job(job_id)
                    if job is None:
                        raise KeyError(f"job not found: {job_id}")
                    enriched = enrich_job(job, settings=cfg)
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
                if progress is not None:
                    for failure in failures:
                        progress.log("error", failure, step_id="enrich.backfill")
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
                rank_workers = cfg.rank_max_concurrency
                _scrape_log(
                    progress,
                    f"Ranking {len(pending_rank)} job(s) vs résumé "
                    f"({rank_workers} parallel LLM workers)…",
                )
                if progress is not None:
                    from agentzero.loops.run_progress import RunProgressAdapter

                    rank_progress = RunProgressAdapter(
                        len(pending_rank),
                        label="Rank vs résumé",
                        run_progress=progress,
                        phase="rank",
                        step_id="rank.batch",
                    )
                else:
                    from agentzero.loops.progress import Progress

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
                if progress is not None:
                    for failure in failures:
                        progress.log("error", failure, step_id="rank.batch")
                result.ranked = len(pending_rank) - len(failures)

        if progress is not None:
            progress.finish()

        return result

    def _enrich_scraped_job(self, job: JobPosting, cfg: Settings) -> JobPosting:
        """Parse comp from description; fetch LinkedIn detail page when salary missing."""
        job = enrich_job(job, settings=cfg)
        if job.comp_min is not None or job.comp_max is not None:
            return job
        if "linkedin" not in job.source.lower():
            return job
        from agentzero.enrich.detail_fetch import fetch_and_merge_detail

        job = fetch_and_merge_detail(job, settings=cfg, allow_browser=True)
        return enrich_job(job, settings=cfg)

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
