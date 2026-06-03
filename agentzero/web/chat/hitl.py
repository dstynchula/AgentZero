"""Execute confirmed pending chat actions via existing web/MCP modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentzero.leads.session import approve_leads, reject_leads
from agentzero.mcp.validation import validate_job_ids
from agentzero.models import normalize_job_id
from agentzero.web.chat.store import ChatStore, PendingAction
from agentzero.web.mutations import (
    JobNotFoundError,
    reject_job,
    update_job_notes,
    update_job_status,
)
from agentzero.web.operator_config import load_operator_config


def execute_pending_action(
    pending: PendingAction,
    *,
    db,
    settings,
    scrape_runner,
    cover_letter_runner,
    operator_config_path: Path,
    cover_letters_dir: Path | None = None,
) -> dict[str, Any]:
    """Run a confirmed mutating tool. Raises on validation errors."""
    name = pending.tool_name
    args = pending.arguments

    if name == "update_job_status":
        job_id = normalize_job_id(str(args.get("job_id", "")))
        job = update_job_status(db, job_id, str(args.get("status", "")))
        return {"job_id": job.job_id, "status": job.status.value}

    if name == "update_job_notes":
        job_id = normalize_job_id(str(args.get("job_id", "")))
        job = update_job_notes(db, job_id, str(args.get("notes", "")))
        return {"job_id": job.job_id, "notes": job.notes or ""}

    if name == "reject_job":
        job_id = normalize_job_id(str(args.get("job_id", "")))
        job = reject_job(db, job_id)
        return {"job_id": job.job_id, "status": job.status.value}

    if name == "start_scrape":
        operator = load_operator_config(operator_config_path)
        ok, message = scrape_runner.start(
            db=db,
            settings=settings,
            operator=operator,
        )
        return {"started": ok, "message": message}

    if name == "generate_cover_letter":
        job_id = normalize_job_id(str(args.get("job_id", "")))
        if db.get_job(job_id) is None:
            raise JobNotFoundError(job_id)
        ok, message = cover_letter_runner.start(
            db=db,
            settings=settings,
            job_id=job_id,
            cover_letters_dir=cover_letters_dir,
        )
        return {"started": ok, "message": message, "job_id": job_id}

    if name == "approve_leads":
        ids = validate_job_ids(list(args.get("job_ids") or []))
        count = approve_leads(db, ids)
        return {"approved": count, "requested": len(ids)}

    if name == "reject_leads":
        ids = validate_job_ids(list(args.get("job_ids") or []))
        count = reject_leads(db, ids)
        return {"rejected": count, "requested": len(ids)}

    raise ValueError(f"unknown pending tool: {name}")


def confirm_pending(
    store: ChatStore,
    session_id: str,
    *,
    db,
    settings,
    scrape_runner,
    cover_letter_runner,
    operator_config_path: Path,
    cover_letters_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute and clear the session's pending action."""
    pending = store.get_pending_action(session_id)
    if pending is None:
        raise LookupError("no pending action")
    result = execute_pending_action(
        pending,
        db=db,
        settings=settings,
        scrape_runner=scrape_runner,
        cover_letter_runner=cover_letter_runner,
        operator_config_path=operator_config_path,
        cover_letters_dir=cover_letters_dir,
    )
    store.clear_pending_action(session_id)
    store.append_message(
        session_id,
        role="assistant",
        content=f"Confirmed: {pending.summary}",
    )
    return {"ok": True, "tool": pending.tool_name, "result": result}


def reject_pending(store: ChatStore, session_id: str) -> dict[str, Any]:
    """Discard the session's pending action."""
    pending = store.get_pending_action(session_id)
    if pending is None:
        raise LookupError("no pending action")
    store.clear_pending_action(session_id)
    store.append_message(
        session_id,
        role="assistant",
        content=f"Cancelled: {pending.summary}",
    )
    return {"ok": True, "cancelled": pending.tool_name}
