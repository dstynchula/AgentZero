"""Validate and normalize raw scraper records into ``JobPosting`` instances."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from agentzero.models import JobPosting, RawRecord

# Per-board field aliases applied before pydantic validation.
SOURCE_ALIASES: dict[str, dict[str, str]] = {
    "default": {
        "job_title": "title",
        "jobTitle": "title",
        "position": "title",
        "company_name": "company",
        "companyName": "company",
        "employer": "company",
        "job_url": "url",
        "jobUrl": "url",
        "link": "url",
        "site": "source",
        "board": "source",
        "salary": "comp_raw",
        "company_rating": "glassdoor_rating",
        "company_reviews_count": "glassdoor_reviews",
        "is_remote": "remote",
        "job_type_remote": "remote",
    },
}

SALARY_RANGE_RE = re.compile(
    r"(?P<currency>[$€£])?\s*"
    r"(?P<min>[\d,]+(?:\.\d+)?)\s*(?:k|K)?"
    r"\s*[-–—to]+\s*"
    r"(?:[$€£])?\s*"
    r"(?P<max>[\d,]+(?:\.\d+)?)\s*(?:k|K)?",
    re.IGNORECASE,
)
SALARY_SINGLE_RE = re.compile(
    r"(?P<currency>[$€£])?\s*(?P<amount>[\d,]+(?:\.\d+)?)\s*(?:k|K)?",
    re.IGNORECASE,
)
CURRENCY_MAP = {"$": "USD", "€": "EUR", "£": "GBP"}


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """Result of validating a single raw record."""

    job: JobPosting | None
    error: str | None = None
    repaired: bool = False
    quarantined: bool = False

    @property
    def ok(self) -> bool:
        return self.job is not None


def apply_aliases(raw: RawRecord, *, source: str) -> RawRecord:
    """Map board-specific keys onto the canonical ``JobPosting`` field names."""
    aliases = {**SOURCE_ALIASES["default"], **SOURCE_ALIASES.get(source, {})}
    out: RawRecord = {}
    for key, value in raw.items():
        target = aliases.get(key, key)
        if target in out and out[target] not in (None, "") and value not in (None, ""):
            continue
        out[target] = value
    if "source" not in out or not str(out.get("source", "")).strip():
        out["source"] = source
    return out


def parse_comp_from_text(text: str) -> tuple[float | None, float | None, str | None]:
    """Parse a salary string into min/max/currency (best effort)."""
    cleaned = text.strip()
    if not cleaned:
        return None, None, None

    match = SALARY_RANGE_RE.search(cleaned)
    if match:
        currency = _currency_symbol(match.group("currency"))
        low = _parse_amount(match.group("min"))
        high = _parse_amount(match.group("max"))
        return low, high, currency

    match = SALARY_SINGLE_RE.search(cleaned)
    if match:
        currency = _currency_symbol(match.group("currency"))
        amount = _parse_amount(match.group("amount"))
        return amount, amount, currency

    return None, None, None


def _currency_symbol(symbol: str | None) -> str | None:
    if not symbol:
        return None
    return CURRENCY_MAP.get(symbol, symbol)


def _parse_amount(raw: str) -> float:
    value = float(raw.replace(",", ""))
    if value < 1000:
        return value * 1000
    return value


def _coerce_types(data: RawRecord) -> RawRecord:
    out = dict(data)
    comp_raw = out.pop("comp_raw", None)
    if comp_raw and not out.get("comp_min") and not out.get("comp_max"):
        low, high, currency = parse_comp_from_text(str(comp_raw))
        out.setdefault("comp_min", low)
        out.setdefault("comp_max", high)
        out.setdefault("currency", currency)
        out["comp_is_estimate"] = True
    if "remote" in out and isinstance(out["remote"], str):
        out["remote"] = out["remote"].strip().lower() in {"true", "yes", "1", "remote"}
    return out


def validate_raw(raw: RawRecord, *, source: str) -> ValidationOutcome:
    """Validate a raw record, applying deterministic alias repair first."""
    mapped = _coerce_types(apply_aliases(raw, source=source))
    try:
        job = JobPosting.model_validate(mapped)
        repaired = mapped != raw
        return ValidationOutcome(job=job, repaired=repaired)
    except ValidationError as exc:
        return ValidationOutcome(job=None, error=str(exc), quarantined=True)


def validate_batch(
    records: list[RawRecord],
    *,
    source: str,
) -> tuple[list[JobPosting], list[tuple[RawRecord, str]], dict[str, float]]:
    """Validate many records; return jobs, quarantine tuples, and health metrics."""
    jobs: list[JobPosting] = []
    quarantined: list[tuple[RawRecord, str]] = []
    valid = repaired = 0
    total = len(records)

    for raw in records:
        outcome = validate_raw(raw, source=source)
        if outcome.ok and outcome.job is not None:
            jobs.append(outcome.job)
            valid += 1
            if outcome.repaired:
                repaired += 1
        else:
            quarantined.append((raw, outcome.error or "unknown validation error"))

    metrics = {
        "total": float(total),
        "valid_pct": (valid / total * 100.0) if total else 100.0,
        "repaired_pct": (repaired / total * 100.0) if total else 0.0,
        "quarantined_pct": (len(quarantined) / total * 100.0) if total else 0.0,
    }
    return jobs, quarantined, metrics


def assert_source_healthy(metrics: dict[str, float], *, min_valid_pct: float = 80.0) -> None:
    """Raise when a source's valid rate drops below the configured threshold."""
    if metrics["total"] > 0 and metrics["valid_pct"] < min_valid_pct:
        raise RuntimeError(
            f"Source health check failed: valid_pct={metrics['valid_pct']:.1f} "
            f"(minimum {min_valid_pct})"
        )
