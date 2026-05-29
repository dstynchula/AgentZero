"""End-to-end scrape -> validate -> enrich -> rank -> draft pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentzero.enrich.pipeline import enrich_job
from agentzero.generate.cover_letter import generate_cover_letter
from agentzero.loops.ralph import run_parallel
from agentzero.rank.matcher import rank_job
from agentzero.scrape.validate import assert_source_healthy, validate_batch

if TYPE_CHECKING:
    from agentzero.ingest.resume import ResumeProfile
    from agentzero.ingest.voice import VoiceProfile
    from agentzero.llm.provider import LLMProvider
    from agentzero.scrape.base import JobSource
    from agentzero.storage.db import Database


@dataclass
class PipelineResult:
    scraped: int = 0
    quarantined: int = 0
    enriched: int = 0
    ranked: int = 0
    drafted: int = 0
    errors: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        db: Database,
        source: JobSource,
        *,
        llm: LLMProvider | None = None,
        max_workers: int = 4,
    ) -> None:
        self._db = db
        self._source = source
        self._llm = llm
        self._max_workers = max_workers

    def run(
        self,
        *,
        profile: ResumeProfile | None = None,
        voice: VoiceProfile | None = None,
    ) -> PipelineResult:
        result = PipelineResult()
        raw_records = list(self._source.fetch())
        jobs, quarantined, metrics = validate_batch(
            raw_records, source=self._source.name, llm=self._llm
        )
        try:
            assert_source_healthy(metrics)
        except RuntimeError as exc:
            result.errors.append(str(exc))

        for raw, error in quarantined:
            self._db.add_quarantine(raw_payload=raw, error=error, source=self._source.name)
        result.quarantined = len(quarantined)

        for job in jobs:
            self._db.upsert_job(job)
            self._db.mark_pipeline(job.job_id, "scrape_status", "done")
        result.scraped = len(jobs)

        def enrich_one(job_id: str) -> None:
            job = self._db.get_job(job_id)
            if job is None:
                return
            enriched = enrich_job(job)
            self._db.upsert_job(enriched)
            self._db.mark_pipeline(job_id, "enrich_status", "done")

        pending_enrich = self._db.list_pending("enrich_status")
        run_parallel(pending_enrich, enrich_one, max_workers=self._max_workers)
        result.enriched = len(pending_enrich)

        if profile and self._llm:
            def rank_one(job_id: str) -> None:
                job = self._db.get_job(job_id)
                if job is None:
                    return
                match = rank_job(job, profile, llm=self._llm)
                updated = job.model_copy(update={"match_score": match.match_score})
                self._db.upsert_job(updated)
                self._db.mark_pipeline(job_id, "rank_status", "done")

            pending_rank = self._db.list_pending("rank_status")
            run_parallel(pending_rank, rank_one, max_workers=self._max_workers)
            result.ranked = len(pending_rank)

        if profile and voice and self._llm:
            def draft_one(job_id: str) -> None:
                job = self._db.get_job(job_id)
                if job is None:
                    return
                generate_cover_letter(job, profile, voice, llm=self._llm)
                self._db.mark_pipeline(job_id, "draft_status", "done")

            pending_draft = self._db.list_pending("draft_status")
            run_parallel(pending_draft, draft_one, max_workers=self._max_workers)
            result.drafted = len(pending_draft)

        return result
