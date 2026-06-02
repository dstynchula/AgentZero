"""AgentZero FastMCP server — local job-hunt tools (stdio trust boundary)."""

from __future__ import annotations

import argparse


def build_server():
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "MCP server requires fastmcp. Install with: pip install -e '.[mcp]'"
        ) from exc

    from agentzero.config import get_settings
    from agentzero.ingest.resume import ingest_resume
    from agentzero.leads.session import (
        approve_leads as approve_leads_fn,
    )
    from agentzero.leads.session import (
        build_run_settings,
        check_board_sessions,
        format_lead_preview,
        job_to_preview_dict,
        list_pending_leads,
        run_lead_scrape,
    )
    from agentzero.leads.session import (
        commit_leads as commit_leads_fn,
    )
    from agentzero.leads.session import (
        reject_leads as reject_leads_fn,
    )
    from agentzero.leads.session import (
        suggest_targets as suggest_targets_fn,
    )
    from agentzero.llm.provider import build_llm_provider
    from agentzero.mcp.validation import validate_job_ids, validate_scrape_tool_args
    from agentzero.mcp.workflow import MCP_SERVER_INSTRUCTIONS, lead_session_workflow_text
    from agentzero.scrape.browser_common import ensure_cdp_for_sites
    from agentzero.scrape.browser_session import session_status_message
    from agentzero.storage.db import Database

    mcp = FastMCP("AgentZero", instructions=MCP_SERVER_INSTRUCTIONS)
    settings = get_settings()

    def _db() -> Database:
        return Database(settings.db_path)

    @mcp.tool
    def lead_session_workflow() -> str:
        """Return the interactive lead-gathering workflow for chat-driven sessions."""
        return lead_session_workflow_text()

    @mcp.tool
    def scrape_status() -> dict:
        """Return job counts from the local database."""
        db = _db()
        try:
            leads = list_pending_leads(db)
            return {
                "jobs": db.count_jobs(),
                "pending_leads": len(leads),
            }
        finally:
            db.close()

    @mcp.tool
    def list_quarantine() -> list:
        """List quarantined scrape records."""
        db = _db()
        try:
            return db.list_quarantine()
        finally:
            db.close()

    @mcp.tool
    def suggest_targets(force_refresh: bool = False) -> dict:
        """Read the résumé and return suggested titles, locations, and comp floor."""
        llm = build_llm_provider()
        targets = suggest_targets_fn(llm, force_refresh=force_refresh)
        return {
            "candidate_name": targets.candidate_name,
            "search_terms": targets.search_terms,
            "locations": targets.locations,
            "remote_preferred": targets.remote_preferred,
            "salary_min": targets.salary_min,
            "summary": targets.summary(),
            "next_step": "Ask the user to confirm or edit titles, remote-only, and comp floor.",
        }

    @mcp.tool
    def check_sessions() -> list[dict]:
        """Probe Indeed/LinkedIn/Glassdoor browser sessions before scraping."""
        ensure_cdp_for_sites(settings)
        results = check_board_sessions(settings)
        out: list[dict] = []
        for probe in results:
            out.append(
                {
                    "site": probe.site,
                    "state": probe.state.value if hasattr(probe.state, "value") else str(probe.state),
                    "ready": probe.exit_code == 0,
                    "listing_count": probe.listing_count,
                    "url": probe.url,
                    "message": session_status_message(probe.site, probe.state),
                    "error": probe.error,
                }
            )
        return out

    @mcp.tool
    def run_scrape(
        search_terms: list[str],
        remote_only: bool = True,
        salary_min: float | None = None,
        results_wanted: int | None = None,
        primary_query_only: bool = False,
    ) -> dict:
        """Scrape job boards, enrich, rank; new roles land as ``lead`` (review in web UI)."""
        terms = validate_scrape_tool_args(
            search_terms,
            salary_min=salary_min,
            results_wanted=results_wanted,
        )
        ensure_cdp_for_sites(settings)
        llm = build_llm_provider()
        targets = suggest_targets_fn(llm, force_refresh=False)
        effective = build_run_settings(
            settings,
            targets.profile,
            search_terms=terms,
            remote_only=remote_only,
            salary_min=salary_min,
            results_wanted=results_wanted,
            primary_query_only=primary_query_only,
        )
        resume = ingest_resume(llm=llm, refresh_search=False)
        db = _db()
        try:
            run = run_lead_scrape(db, effective, llm=llm, profile=resume)
            return {
                "scraped": run.pipeline.scraped,
                "ranked": run.pipeline.ranked,
                "quarantined": run.pipeline.quarantined,
                "errors": run.pipeline.errors,
                "lead_count": run.lead_count,
                "preview": format_lead_preview(run.leads),
                "leads": [job_to_preview_dict(job) for job in run.leads],
                "next_step": "Present preview to the user; ask which job_ids to commit_leads.",
            }
        finally:
            db.close()

    @mcp.tool
    def list_leads() -> list[dict]:
        """List all jobs awaiting approval (status=lead)."""
        db = _db()
        try:
            return [job_to_preview_dict(job) for job in list_pending_leads(db)]
        finally:
            db.close()

    @mcp.tool
    def approve_leads(job_ids: list[str]) -> dict:
        """Promote leads to active status (visible in web tracker)."""
        ids = validate_job_ids(job_ids)
        db = _db()
        try:
            count = approve_leads_fn(db, ids)
            return {"approved": count, "requested": len(ids)}
        finally:
            db.close()

    @mcp.tool
    def reject_leads(job_ids: list[str]) -> dict:
        """Reject leads (kept in DB for dedupe, hidden in default web UI)."""
        ids = validate_job_ids(job_ids)
        db = _db()
        try:
            count = reject_leads_fn(db, ids)
            return {"rejected": count, "requested": len(ids)}
        finally:
            db.close()

    @mcp.tool
    def commit_leads(job_ids: list[str]) -> dict:
        """Approve selected leads (promote LEAD → NEW in SQLite)."""
        ids = validate_job_ids(job_ids)
        db = _db()
        try:
            result = commit_leads_fn(db, settings, ids)
            return {
                "approved": result.approved,
                "requested": len(ids),
                "tracker_note": (
                    "Jobs are in SQLite. Open the web UI (docker compose up web) "
                    "to review and edit status/notes."
                ),
            }
        finally:
            db.close()

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentZero MCP server")
    parser.add_argument("--stdio", action="store_true", help="Run MCP over stdio")
    args = parser.parse_args()
    if not args.stdio:
        parser.error("Pass --stdio to run the MCP server (or use --help).")
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
