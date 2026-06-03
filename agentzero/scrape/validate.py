"""Validate and normalize raw scraper records into ``JobPosting`` instances."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import ValidationError

from agentzero.llm.json_util import parse_llm_json_object_loose
from agentzero.models import JobPosting, RawRecord

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

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
        "apply_url": "apply_url",
        "application_url": "apply_url",
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

_PLACEHOLDER_COMPANY = frozenset({"", "unknown", "n/a", "na", "tbd", "none"})
_MIN_DESCRIPTION_LEN = 40


def has_min_role_context(mapped: RawRecord) -> bool:
    """True when the listing has location, salary hint, or enough description text."""
    location = str(mapped.get("location") or "").strip()
    if location:
        return True
    comp_raw = str(mapped.get("comp_raw") or "").strip()
    if comp_raw:
        return True
    if mapped.get("comp_min") is not None or mapped.get("comp_max") is not None:
        return True
    description = str(mapped.get("description") or "").strip()
    return len(description) >= _MIN_DESCRIPTION_LEN


def is_placeholder_company(company: str) -> bool:
    return company.strip().lower() in _PLACEHOLDER_COMPANY


def reject_incomplete_raw(mapped: RawRecord) -> str | None:
    """Return a quarantine reason when company/role basics are missing."""
    company = str(mapped.get("company") or "").strip()
    title = str(mapped.get("title") or "").strip()
    url = str(mapped.get("url") or "").strip()
    if not company or is_placeholder_company(company):
        return "missing or placeholder company"
    if not title:
        return "missing title"
    if not url:
        return "missing url"
    if not has_min_role_context(mapped):
        return "insufficient role context (need location, description, or comp hint)"
    return None


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
    incomplete = reject_incomplete_raw(mapped)
    if incomplete:
        return ValidationOutcome(job=None, error=incomplete, quarantined=True)
    try:
        job = JobPosting.model_validate(mapped)
        repaired = mapped != raw
        return ValidationOutcome(job=job, repaired=repaired)
    except ValidationError as exc:
        return ValidationOutcome(job=None, error=str(exc), quarantined=True)


def build_llm_repair_prompt(raw: RawRecord, error: str, *, source: str) -> str:
    """Build the user prompt for an LLM repair pass."""
    payload = {
        "source": source,
        "raw_record": raw,
        "validation_error": error,
        "target_schema": JobPosting.model_json_schema(),
        "instructions": (
            "Return ONLY a JSON object with canonical JobPosting fields "
            "(title, company, url, source required). Do not wrap in markdown."
        ),
    }
    return json.dumps(payload, indent=2)


def llm_repair_raw(
    raw: RawRecord,
    *,
    source: str,
    error: str,
    llm: LLMProvider,
) -> RawRecord:
    """Ask the LLM to return a corrected raw record dict."""
    response = llm.complete(
        system=(
            "You normalize job listing data. Respond with a single JSON object only, "
            "using field names from the provided schema."
        ),
        user=build_llm_repair_prompt(raw, error, source=source),
    )
    text = response.strip()
    parsed = parse_llm_json_object_loose(text)
    return parsed


def validate_raw_with_llm(
    raw: RawRecord,
    *,
    source: str,
    llm: LLMProvider | None = None,
) -> ValidationOutcome:
    """Validate with deterministic repair first, then optional LLM repair."""
    outcome = validate_raw(raw, source=source)
    if outcome.ok or llm is None:
        return outcome

    try:
        repaired_raw = llm_repair_raw(
            raw, source=source, error=outcome.error or "validation failed", llm=llm
        )
        second = validate_raw(repaired_raw, source=source)
        if second.ok:
            return ValidationOutcome(job=second.job, repaired=True)
        return ValidationOutcome(
            job=None,
            error=second.error or outcome.error,
            quarantined=True,
        )
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        return ValidationOutcome(
            job=None,
            error=f"LLM repair failed: {exc}",
            quarantined=True,
        )


def validate_batch(
    records: list[RawRecord],
    *,
    source: str,
    llm: LLMProvider | None = None,
) -> tuple[list[JobPosting], list[tuple[RawRecord, str]], dict[str, float]]:
    """Validate many records; return jobs, quarantine tuples, and health metrics."""
    jobs: list[JobPosting] = []
    quarantined: list[tuple[RawRecord, str]] = []
    valid = repaired = 0
    total = len(records)

    for raw in records:
        outcome = (
            validate_raw_with_llm(raw, source=source, llm=llm)
            if llm is not None
            else validate_raw(raw, source=source)
        )
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
