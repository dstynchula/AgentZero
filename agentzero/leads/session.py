"""Orchestrate a conversational lead-gathering scrape run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentzero.ingest.search_interactive import format_search_summary
from agentzero.ingest.search_profile import (
    ResumeSearchProfile,
    apply_search_profile,
    resolve_search_from_resume,
    save_search_profile,
)
from agentzero.loops.pipeline import Pipeline, PipelineResult
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.scrape.remote_policy import apply_remote_only_settings

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.ingest.resume import ResumeProfile
    from agentzero.llm.provider import LLMProvider
    from agentzero.scrape.session_probe import SessionProbeResult
    from agentzero.storage.db import Database


@dataclass(frozen=True, slots=True)
class SearchTargets:
    """Résumé-derived search suggestions for the operator to confirm."""

    search_terms: list[str]
    locations: list[str]
    remote_preferred: bool
    salary_min: float | None
    candidate_name: str | None
    profile: ResumeSearchProfile

    def summary(self) -> str:
        return format_search_summary(self.profile)

    def safe_log_line(self) -> str:
        """Single-line CLI status without résumé-derived PII (names, titles, locations, comp)."""
        comp = "set" if self.salary_min is not None else "not set"
        return (
            f"Résumé targets ready: {len(self.search_terms)} title(s), "
            f"{len(self.locations)} location(s), "
            f"remote={'yes' if self.remote_preferred else 'no'}, comp floor {comp}."
        )


@dataclass(frozen=True, slots=True)
class LeadRunResult:
    pipeline: PipelineResult
    leads: list[JobPosting] = field(default_factory=list)

    @property
    def lead_count(self) -> int:
        return len(self.leads)


def suggest_targets(
    llm: LLMProvider,
    *,
    force_refresh: bool = False,
) -> SearchTargets:
    """Read the résumé and infer suggested titles, locations, and comp floor."""
    from agentzero.ingest.resume import ingest_resume

    profile = resolve_search_from_resume(
        llm=llm,
        force_refresh=force_refresh,
        prefer_snapshot=not force_refresh,
    )
    resume = ingest_resume(llm=llm, refresh_search=False)
    remote = bool(profile.remote_preferred) or all(
        "remote" in loc.lower() for loc in profile.locations
    )
    return SearchTargets(
        search_terms=list(profile.search_terms),
        locations=list(profile.locations),
        remote_preferred=remote,
        salary_min=profile.salary_min,
        candidate_name=resume.name,
        profile=profile,
    )


def build_run_settings(
    base: Settings,
    profile: ResumeSearchProfile,
    *,
    search_terms: list[str] | None = None,
    locations: list[str] | None = None,
    remote_only: bool | None = None,
    salary_min: float | None = None,
    results_wanted: int | None = None,
    primary_query_only: bool | None = None,
) -> Settings:
    """Merge operator-confirmed targets into settings for this run."""
    from datetime import UTC, datetime

    from agentzero.ingest.work_mode import apply_work_mode_selection, selection_from_work_mode

    terms = search_terms or profile.search_terms
    remote = remote_only if remote_only is not None else base.remote_only
    if remote:
        selection = selection_from_work_mode("remote")
    else:
        locs = locations or profile.locations
        selection = selection_from_work_mode("in_office", office_locations=locs)

    floor = salary_min if salary_min is not None else profile.salary_min
    refined = profile.model_copy(
        update={
            "search_terms": terms,
            "salary_min": floor,
            "salary_max": None,
            "updated_at": datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }
    )
    refined = apply_work_mode_selection(refined, selection)
    save_search_profile(refined)

    merged = apply_search_profile(base, refined)
    if results_wanted is not None:
        merged = merged.model_copy(update={"results_wanted": results_wanted})
    if primary_query_only is not None:
        merged = merged.model_copy(update={"scrape_primary_query_only": primary_query_only})
    if remote_only is not None:
        merged = merged.model_copy(update={"remote_only": remote_only})
    if salary_min is not None:
        merged = merged.model_copy(update={"salary_min": salary_min})
    return apply_remote_only_settings(merged)


def check_board_sessions(settings: Settings) -> list[SessionProbeResult]:
    """Probe browser job boards and report login/CAPTCHA readiness."""
    from agentzero.scrape.session_probe import probe_browser_session

    raw = settings.scrape_browser_sites
    if isinstance(raw, str):
        sites = [s.strip().lower() for s in raw.split(",") if s.strip()]
    else:
        sites = [s.strip().lower() for s in raw if s.strip()]
    return [probe_browser_session(settings, site) for site in sites]


def run_lead_scrape(
    db: Database,
    settings: Settings,
    *,
    llm: LLMProvider | None,
    profile: ResumeProfile | None,
) -> LeadRunResult:
    """Scrape, enrich, rank; new listings land as ``LEAD`` (review in web UI before promoting)."""
    from agentzero.scrape.factory import build_scrape_source

    known_ids = set(db.list_job_ids())
    source = build_scrape_source(settings, llm=None)
    pipeline = Pipeline(
        db,
        source,
        settings=settings,
        llm=llm,
        max_workers=settings.max_concurrency,
    )
    result = pipeline.run(profile=profile, new_status=ApplicationStatus.LEAD)
    leads = [
        job
        for job in db.list_jobs()
        if job.status == ApplicationStatus.LEAD and job.job_id not in known_ids
    ]
    leads.sort(key=lambda j: (j.match_score is None, -(j.match_score or 0)))
    return LeadRunResult(pipeline=result, leads=leads)


def list_pending_leads(db: Database) -> list[JobPosting]:
    """All jobs awaiting operator approval (``status=lead``)."""
    leads = [job for job in db.list_jobs() if job.status == ApplicationStatus.LEAD]
    leads.sort(key=lambda j: (j.match_score is None, -(j.match_score or 0)))
    return leads


def approve_leads(db: Database, job_ids: list[str]) -> int:
    """Promote ``LEAD`` rows to ``NEW`` (active leads visible in the web tracker)."""
    updated = 0
    for job_id in job_ids:
        job = db.get_job(job_id)
        if job is None or job.status != ApplicationStatus.LEAD:
            continue
        db.upsert_job(job.model_copy(update={"status": ApplicationStatus.NEW}))
        updated += 1
    return updated


def reject_leads(db: Database, job_ids: list[str]) -> int:
    """Mark ``LEAD`` rows as ``REJECTED`` (kept for dedupe, hidden in default web UI)."""
    updated = 0
    for job_id in job_ids:
        job = db.get_job(job_id)
        if job is None or job.status != ApplicationStatus.LEAD:
            continue
        db.upsert_job(job.model_copy(update={"status": ApplicationStatus.REJECTED}))
        updated += 1
    return updated


@dataclass(frozen=True, slots=True)
class CommitLeadsResult:
    approved: int


def commit_leads(
    db: Database,
    settings: Settings,
    job_ids: list[str],
) -> CommitLeadsResult:
    """Approve selected leads (promote ``LEAD`` → ``NEW`` in SQLite)."""
    _ = settings  # signature kept for MCP/CLI compatibility
    approved = approve_leads(db, job_ids)
    return CommitLeadsResult(approved=approved)


def job_to_preview_dict(job: JobPosting) -> dict[str, object]:
    """JSON-serializable summary for MCP / CLI preview."""
    return {
        "job_id": job.job_id,
        "title": job.title,
        "company": job.company,
        "source": job.source,
        "location": job.location or "",
        "remote": job.remote,
        "comp_min": job.comp_min,
        "comp_max": job.comp_max,
        "match_score": job.match_score,
        "match_rationale": (job.match_rationale or "")[:200],
        "url": job.url,
        "status": job.status.value,
    }


def _markdown_table_cell(value: str) -> str:
    """Escape pipe/newline so job board text does not break preview tables."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def format_lead_preview(leads: list[JobPosting]) -> str:
    """Markdown table for chat / terminal review."""
    if not leads:
        return "No new leads from this run."
    lines = [
        "| Score | Title | Company | Source |",
        "| --- | --- | --- | --- |",
    ]
    for job in leads:
        score = f"{job.match_score:.2f}" if job.match_score is not None else "—"
        lines.append(
            f"| {score} | {_markdown_table_cell(job.title)} | "
            f"{_markdown_table_cell(job.company)} | {_markdown_table_cell(job.source)} |"
        )
    lines.append("")
    lines.append(
        f"**{len(leads)}** lead(s) — approve to promote (view at http://localhost:8080 when web is up)."
    )
    return "\n".join(lines)
