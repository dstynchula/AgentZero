"""Tool definitions and executors for the web chat assistant."""

from __future__ import annotations

from typing import Any

from agentzero.ingest.search_profile import load_search_profile
from agentzero.leads.session import list_pending_leads
from agentzero.models import normalize_job_id
from agentzero.web.jobs import job_detail_for_ui, list_jobs_for_ui
from agentzero.web.search_titles import search_profile_summary

READ_TOOL_NAMES = frozenset(
    {
        "list_jobs",
        "get_job",
        "get_search_profile_summary",
        "get_scraper_status",
    }
)

WRITE_TOOL_NAMES = frozenset(
    {
        "update_job_status",
        "update_job_notes",
        "reject_job",
        "start_scrape",
        "generate_cover_letter",
        "approve_leads",
        "reject_leads",
    }
)

MUTATING_TOOL_NAMES = WRITE_TOOL_NAMES

CHAT_SYSTEM_PROMPT = """You are AgentZero, a job-search assistant for a single operator.
You can read the SQLite job tracker, résumé-derived search profile, and scraper status.
Discuss fit and priorities clearly. For any change (status, notes, reject, scrape, cover letter,
lead approve/reject), call the appropriate tool — the operator must Confirm in the UI before it runs.
Never claim an action succeeded until the operator confirms. Be concise."""


def openai_tool_specs() -> list[dict[str, Any]]:
    """Return OpenAI-compatible tool definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_jobs",
                "description": "List jobs in the tracker (excludes rejected by default).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_rejected": {"type": "boolean"},
                        "status_filter": {
                            "type": "string",
                            "description": "Filter by status, e.g. lead or new",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_job",
                "description": "Full detail for one job by job_id.",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_search_profile_summary",
                "description": "Résumé-derived search titles, locations, and comp floor.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_scraper_status",
                "description": "Background scrape runner state and job counts.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_job_status",
                "description": "Change application status for a job (requires Confirm).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["job_id", "status"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_job_notes",
                "description": "Update free-text notes on a job (requires Confirm).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["job_id", "notes"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reject_job",
                "description": "Mark a job rejected (requires Confirm).",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "start_scrape",
                "description": "Start background scrape from web scraper page (requires Confirm).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_cover_letter",
                "description": "Generate cover letter for a job in background (requires Confirm).",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "approve_leads",
                "description": "Promote LEAD jobs to NEW (requires Confirm).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["job_ids"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reject_leads",
                "description": "Reject LEAD jobs (requires Confirm).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["job_ids"],
                },
            },
        },
    ]


def pending_action_summary(tool_name: str, arguments: dict[str, Any]) -> str:
    """Human-readable summary for the HITL confirm card."""
    if tool_name == "update_job_status":
        return f"Set status on {arguments.get('job_id')} → {arguments.get('status')}"
    if tool_name == "update_job_notes":
        job_id = arguments.get("job_id")
        notes = str(arguments.get("notes", ""))[:80]
        return f"Update notes on {job_id}: {notes!r}"
    if tool_name == "reject_job":
        return f"Reject job {arguments.get('job_id')}"
    if tool_name == "start_scrape":
        return "Start background job scrape"
    if tool_name == "generate_cover_letter":
        return f"Generate cover letter for {arguments.get('job_id')}"
    if tool_name == "approve_leads":
        ids = arguments.get("job_ids") or []
        return f"Approve {len(ids)} lead(s): {', '.join(ids[:5])}"
    if tool_name == "reject_leads":
        ids = arguments.get("job_ids") or []
        return f"Reject {len(ids)} lead(s): {', '.join(ids[:5])}"
    return f"{tool_name}({arguments})"


def execute_read_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    db,
    scrape_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a read-only tool immediately."""
    if name == "list_jobs":
        rows = list_jobs_for_ui(
            db,
            include_rejected=bool(arguments.get("include_rejected")),
            status_filter=arguments.get("status_filter"),
        )
        return {"jobs": rows, "count": len(rows)}
    if name == "get_job":
        job_id = normalize_job_id(str(arguments.get("job_id", "")))
        detail = job_detail_for_ui(db, job_id)
        if detail is None:
            return {"error": "job not found", "job_id": job_id}
        return {"job": detail}
    if name == "get_search_profile_summary":
        snapshot = load_search_profile()
        return {"profile": search_profile_summary(snapshot)}
    if name == "get_scraper_status":
        pending = list_pending_leads(db)
        payload = {
            "jobs": db.count_jobs(),
            "pending_leads": len(pending),
        }
        if scrape_snapshot is not None:
            payload["scrape"] = scrape_snapshot
        return payload
    raise ValueError(f"unknown read tool: {name}")
