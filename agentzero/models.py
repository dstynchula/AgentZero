"""Core domain models shared across scrape, enrich, rank, and apply pipelines."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

# Scraper output before validation / normalization (T07).
RawRecord = dict[str, Any]


class ApplicationStatus(StrEnum):
    """Lifecycle status for a tracked job application."""

    LEAD = "lead"
    NEW = "new"
    REVIEWED = "reviewed"
    QUEUED = "queued"
    CONTACTED = "contacted"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    REJECTED = "rejected"
    OFFER = "offer"


def stable_job_id(*, source: str, company: str, title: str, url: str) -> str:
    """Deterministic id for deduplication across boards and loop re-runs."""
    parts = (source, company, title, url)
    key = "|".join(_normalize_id_part(p) for p in parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _normalize_id_part(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip().lower())
    return collapsed


class JobPosting(BaseModel):
    """Normalized job listing stored in SQLite and exported to CSV / Sheets."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    url: str = Field(min_length=1)
    source: str = Field(min_length=1)

    comp_min: float | None = None
    comp_max: float | None = None
    currency: str | None = None
    comp_is_estimate: bool = False
    company_size: str | None = None
    glassdoor_rating: float | None = None
    glassdoor_reviews: int | None = None
    date_posted: date | datetime | None = None
    location: str | None = None
    remote: bool | None = None
    description: str | None = None
    careers_url: str | None = None
    match_score: float | None = None
    match_rationale: str | None = None
    status: ApplicationStatus = ApplicationStatus.NEW
    date_first_contacted: date | None = None
    date_applied: date | None = None
    notes: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def job_id(self) -> str:
        return stable_job_id(
            source=self.source,
            company=self.company,
            title=self.title,
            url=self.url,
        )

    @field_validator("url")
    @classmethod
    def url_is_http(cls, value: str) -> str:
        lowered = value.strip().lower()
        if not (lowered.startswith("http://") or lowered.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return value.strip()

    @field_validator("glassdoor_rating")
    @classmethod
    def rating_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 5.0:
            raise ValueError("glassdoor_rating must be between 0 and 5")
        return value
