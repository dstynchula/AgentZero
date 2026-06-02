"""Application tracking helpers — row import, applied-job protection, lookups."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentzero.apply.tracker_fields import (
    merge_user_fields_from_row,
    parse_tracker_date,
    parse_tracker_status,
)
from agentzero.models import ApplicationStatus, JobPosting, stable_job_id

if TYPE_CHECKING:
    from agentzero.storage.db import Database

_TRACKER_IDENTITY_COLUMNS = ("company", "title", "url", "source", "job_id")
_PLACEHOLDER_URL = "https://applied.local/tracker"


def is_applied(job: JobPosting) -> bool:
    """True when the operator has marked this role as applied."""
    if job.date_applied is not None:
        return True
    return job.status in {ApplicationStatus.APPLIED, ApplicationStatus.INTERVIEWING}


def is_application_locked(job: JobPosting) -> bool:
    """True when maintenance scripts must not delete this row (not export policy)."""
    return job.status in {
        ApplicationStatus.APPLIED,
        ApplicationStatus.INTERVIEWING,
        ApplicationStatus.REJECTED,
        ApplicationStatus.OFFER,
    } or job.date_applied is not None


def list_applied_jobs(db: Database) -> list[JobPosting]:
    return [job for job in db.list_jobs() if is_applied(job)]


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


@dataclass(slots=True)
class _JobIndex:
    """In-memory lookup so a batch import deserializes jobs only once."""

    by_id: dict[str, JobPosting]
    by_url: dict[str, JobPosting]
    by_company_title: dict[tuple[str, str], JobPosting]

    @classmethod
    def from_jobs(cls, jobs: list[JobPosting]) -> _JobIndex:
        index = cls(by_id={}, by_url={}, by_company_title={})
        for job in jobs:
            index.add(job)
        return index

    def add(self, job: JobPosting) -> None:
        self.by_id[job.job_id] = job
        self.by_url[job.url.rstrip("/")] = job
        key = (_normalize_match_text(job.company), _normalize_match_text(job.title))
        self.by_company_title[key] = job

    def match(self, row: dict[str, str]) -> JobPosting | None:
        job_id = str(row.get("job_id") or "").strip()
        if job_id and job_id in self.by_id:
            return self.by_id[job_id]

        url = str(row.get("url") or "").strip()
        if url.startswith(("http://", "https://")):
            found = self.by_url.get(url.rstrip("/"))
            if found is not None:
                return found

        company = _normalize_match_text(str(row.get("company") or ""))
        title = _normalize_match_text(str(row.get("title") or ""))
        if company and title:
            return self.by_company_title.get((company, title))
        return None


def find_job_for_tracker_row(db: Database, row: dict[str, str]) -> JobPosting | None:
    """Resolve a tracker row to an existing DB job (job_id, URL, or company+title)."""
    return _JobIndex.from_jobs(db.list_jobs()).match(row)


def _placeholder_url(*, company: str, title: str, source: str) -> str:
    key = stable_job_id(source=source, company=company, title=title, url=company + title)
    return f"{_PLACEHOLDER_URL}/{key}"


def job_from_tracker_row(row: dict[str, str]) -> JobPosting | None:
    """Build a minimal job from tracker identity columns (for restored application rows)."""
    company = str(row.get("company") or "").strip()
    title = str(row.get("title") or "").strip()
    if not company or not title:
        return None

    url = str(row.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        source = str(row.get("source") or "tracker").strip() or "tracker"
        url = _placeholder_url(company=company, title=title, source=source)

    source = str(row.get("source") or "tracker").strip() or "tracker"
    payload: dict = {
        "company": company,
        "title": title,
        "url": url,
        "source": source,
    }

    for field in (
        "location",
        "remote",
        "comp_min",
        "comp_max",
        "currency",
        "company_size",
        "glassdoor_rating",
        "glassdoor_reviews",
        "match_score",
        "match_rationale",
        "notes",
    ):
        raw = row.get(field)
        if raw is None or str(raw).strip() == "":
            continue
        if field == "remote":
            payload[field] = str(raw).strip().lower() in {"true", "yes", "1", "remote"}
        elif field in {"comp_min", "comp_max", "glassdoor_rating", "match_score"}:
            try:
                value = float(str(raw).replace(",", "").replace("$", ""))
            except ValueError:
                continue
            if field == "match_score":
                value = max(0.0, min(1.0, value))
            payload[field] = value
        elif field == "glassdoor_reviews":
            try:
                payload[field] = int(float(str(raw).replace(",", "")))
            except ValueError:
                continue
        else:
            payload[field] = str(raw).strip()

    date_applied = parse_tracker_date(row.get("date_applied"))
    if date_applied is not None:
        payload["date_applied"] = date_applied
    date_contacted = parse_tracker_date(row.get("date_first_contacted"))
    if date_contacted is not None:
        payload["date_first_contacted"] = date_contacted

    status = parse_tracker_status(row.get("status"))
    if status is not None:
        payload["status"] = status
    elif date_applied is not None:
        payload["status"] = ApplicationStatus.APPLIED

    return JobPosting.model_validate(payload)


@dataclass(frozen=True, slots=True)
class TrackerImportResult:
    updated: int = 0
    created: int = 0
    skipped: int = 0
    rows_read: int = 0


def import_tracker_rows(
    db: Database,
    rows: list[dict[str, str]],
    *,
    search_terms: list[str] | None = None,
    dry_run: bool = False,
) -> TrackerImportResult:
    """Import application tracking + optional new jobs from tracker rows.

    When ``dry_run`` is set, no writes occur but the returned counts match what a
    real import would produce (the in-memory index is still advanced so duplicate
    rows are not double-counted).
    """
    from agentzero.scrape.title_filter import title_matches_search

    updated = 0
    created = 0
    skipped = 0
    index = _JobIndex.from_jobs(db.list_jobs())

    for row in rows:
        if not any(str(row.get(col) or "").strip() for col in _TRACKER_IDENTITY_COLUMNS):
            skipped += 1
            continue

        existing = index.match(row)
        if existing is not None:
            merged, changed = merge_user_fields_from_row(existing, row)
            if changed:
                if not dry_run:
                    db.upsert_job(merged)
                index.add(merged)
                updated += 1
            continue

        applied_date = parse_tracker_date(row.get("date_applied"))
        has_tracking = applied_date is not None or parse_tracker_status(row.get("status")) is not None
        if not has_tracking:
            skipped += 1
            continue

        title = str(row.get("title") or "").strip()
        if (
            search_terms
            and title
            and applied_date is None
            and not title_matches_search(title, search_terms)
        ):
            skipped += 1
            continue

        job = job_from_tracker_row(row)
        if job is None:
            skipped += 1
            continue
        if not dry_run:
            db.upsert_job(job)
        index.add(job)
        created += 1

    return TrackerImportResult(
        updated=updated,
        created=created,
        skipped=skipped,
        rows_read=len(rows),
    )


def parse_tracker_row(header: list[str], values: list[str]) -> dict[str, str]:
    """Map a header + values row to column names (empty cells → ``""``)."""
    out: dict[str, str] = {}
    for index, name in enumerate(header):
        if index < len(values):
            out[name] = values[index].strip()
        else:
            out[name] = ""
    return out


def rows_from_tabular_values(values: list[list[str]]) -> list[dict[str, str]]:
    if not values:
        return []
    header = values[0]
    return [parse_tracker_row(header, row) for row in values[1:] if any(cell.strip() for cell in row)]


def tracker_rows_with_applications(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Rows that carry application context (date_applied or applied-like status)."""
    applied: list[dict[str, str]] = []
    for row in rows:
        if parse_tracker_date(row.get("date_applied")):
            applied.append(row)
            continue
        status = parse_tracker_status(row.get("status"))
        if status in {
            ApplicationStatus.APPLIED,
            ApplicationStatus.INTERVIEWING,
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
        }:
            applied.append(row)
    return applied
