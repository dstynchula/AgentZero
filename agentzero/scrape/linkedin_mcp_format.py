"""Format LinkedIn pull results for MCP tools."""

from __future__ import annotations

from typing import Any

from agentzero.models import RawRecord, stable_job_id


def raw_record_to_preview(record: RawRecord) -> dict[str, Any]:
    """Compact row for operator review."""
    company = str(record.get("company") or "")
    title = str(record.get("title") or "")
    url = str(record.get("url") or "")
    source = str(record.get("source") or "linkedin")
    job_id = stable_job_id(source=source, company=company, title=title, url=url)
    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "url": url,
        "location": record.get("location") or "",
        "remote": record.get("remote"),
        "comp_raw": record.get("comp_raw"),
        "source": source,
    }


def format_pull_result(
    *,
    url: str,
    records: list[RawRecord],
    sections: dict[str, str] | None = None,
    login_required: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    """MCP-friendly payload for pull_linkedin_jobs."""
    previews = [raw_record_to_preview(r) for r in records]
    job_ids = [p["job_id"] for p in previews]
    body: dict[str, Any] = {
        "url": url,
        "job_ids": job_ids,
        "count": len(previews),
        "jobs": previews,
        "login_required": login_required,
    }
    if sections:
        body["sections"] = sections
    if error:
        body["error"] = error
    return body


def format_job_details(
    *,
    url: str,
    html: str,
    record: RawRecord | None = None,
) -> dict[str, Any]:
    """Detail tool response with raw page text."""
    sections: dict[str, str] = {"job_page": html[:120_000]}
    if record:
        sections["parsed"] = str(raw_record_to_preview(record))
    out: dict[str, Any] = {"url": url, "sections": sections}
    if record:
        out["job_id"] = raw_record_to_preview(record)["job_id"]
    return out
