"""LinkedIn jobs MCP server — pull-first job search (stdio trust boundary)."""

from __future__ import annotations

import argparse
import threading
from datetime import date
from typing import Any

_BROWSER_LOCK = threading.Lock()
_SERVICE: object | None = None

LINKEDIN_MCP_INSTRUCTIONS = """\
LinkedIn Jobs MCP — pull LinkedIn listings only.

Primary tool: pull_linkedin_jobs (search + preview). Set persist_leads=true only after the operator confirms.

Also: get_job_details, check_linkedin_session, close_session.
Apply tools (HITL): get_apply_links, record_application — never auto-submit.

One LinkedIn browser session at a time. Do not run while AgentZero run_scrape is active.
Login: python scripts/login_job_boards.py --site linkedin
"""


def build_server():
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "LinkedIn MCP requires fastmcp. Install with: pip install -e '.[mcp]'"
        ) from exc

    from agentzero.config import get_settings
    from agentzero.scrape.linkedin_jobs import LinkedInJobsService
    from agentzero.scrape.linkedin_mcp_format import format_job_details, format_pull_result
    from agentzero.scrape.session_probe import probe_browser_session

    mcp = FastMCP("LinkedInJobs", instructions=LINKEDIN_MCP_INSTRUCTIONS)
    settings = get_settings()

    def _service() -> LinkedInJobsService:
        global _SERVICE
        if _SERVICE is None:
            _SERVICE = LinkedInJobsService(settings)
        return _SERVICE  # type: ignore[return-value]

    @mcp.tool
    def pull_linkedin_jobs(
        persist_leads: bool = False,
    ) -> dict[str, Any]:
        """Search LinkedIn with configured profile; return preview rows (optional SQLite persist)."""
        with _BROWSER_LOCK:
            result = _service().search()
        payload = format_pull_result(
            url=result.url,
            records=result.records,
            login_required=result.login_required,
            error=result.error,
        )
        if persist_leads and result.records and not result.login_required:
            from agentzero.models import ApplicationStatus
            from agentzero.scrape.validate import validate_raw
            from agentzero.storage.db import Database

            db = Database(settings.db_path)
            try:
                stored = 0
                for raw in result.records:
                    validated = validate_raw(raw, source="linkedin")
                    if validated.job is None:
                        continue
                    job = validated.job.model_copy(update={"status": ApplicationStatus.LEAD})
                    db.upsert_job(job)
                    stored += 1
                payload["persisted"] = stored
            finally:
                db.close()
        return payload

    @mcp.tool
    def get_job_details(job_url: str) -> dict[str, Any]:
        """Fetch a LinkedIn job posting page by URL."""
        with _BROWSER_LOCK:
            html = _service().get_job_details_html(job_url)
        if not html:
            return {"url": job_url, "error": "detail_fetch_failed", "sections": {}}
        return format_job_details(url=job_url, html=html)

    @mcp.tool
    def check_linkedin_session() -> dict[str, Any]:
        """Probe LinkedIn login/CAPTCHA readiness."""
        probe = probe_browser_session(settings, "linkedin")
        return {
            "site": probe.site,
            "state": probe.state.value,
            "url": probe.url,
            "listing_count": probe.listing_count,
            "error": probe.error,
        }

    @mcp.tool
    def close_session() -> dict[str, str]:
        """Release lock; browsers are closed after each tool call."""
        return {"status": "ok", "note": "No persistent browser held between tool calls."}

    @mcp.tool
    def get_apply_links(job_id: str) -> dict[str, Any]:
        """Return apply URLs for a job in SQLite (HITL)."""
        from agentzero.storage.db import Database

        db = Database(settings.db_path)
        try:
            job = db.get_job(job_id.strip())
            if job is None:
                return {"error": "job_not_found", "job_id": job_id}
            return {
                "job_id": job.job_id,
                "url": job.url,
                "apply_url": job.apply_url,
                "easy_apply_url": job.easy_apply_url,
                "easy_apply": job.easy_apply,
                "title": job.title,
                "company": job.company,
            }
        finally:
            db.close()

    @mcp.tool
    def record_application(
        job_id: str,
        applied_date: str | None = None,
    ) -> dict[str, Any]:
        """Mark a job as applied with optional ISO date (YYYY-MM-DD). HITL only."""
        from agentzero.apply.tracking import is_applied
        from agentzero.models import ApplicationStatus
        from agentzero.storage.db import Database

        jid = job_id.strip()
        db = Database(settings.db_path)
        try:
            job = db.get_job(jid)
            if job is None:
                return {"error": "job_not_found", "job_id": jid}
            when: date | None = None
            if applied_date:
                when = date.fromisoformat(applied_date.strip())
            else:
                when = date.today()
            updated = job.model_copy(
                update={"status": ApplicationStatus.APPLIED, "date_applied": when}
            )
            db.upsert_job(updated)
            return {
                "job_id": jid,
                "date_applied": when.isoformat(),
                "status": updated.status.value,
                "was_applied": is_applied(job),
            }
        finally:
            db.close()

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn jobs MCP server")
    parser.add_argument("--stdio", action="store_true", help="Run MCP over stdio")
    args = parser.parse_args()
    if not args.stdio:
        parser.error("Pass --stdio to run the LinkedIn jobs MCP server.")
    build_server().run()


if __name__ == "__main__":
    main()
