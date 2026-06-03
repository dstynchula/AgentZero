"""Tests for LinkedIn jobs MCP server."""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agentzero.config import Settings
from agentzero.linkedin_mcp_server import LINKEDIN_MCP_INSTRUCTIONS, build_server
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.scrape.browser_session import SessionState
from agentzero.scrape.linkedin_jobs import LinkedInSearchResult
from agentzero.scrape.session_probe import SessionProbeResult


def _call_tool(server, name: str, arguments: dict | None = None):
    import asyncio

    async def _run():
        result = await server.call_tool(name, arguments or {})
        content = result.structured_content
        if isinstance(content, dict) and set(content.keys()) == {"result"}:
            return content["result"]
        return content

    return asyncio.run(_run())


@pytest.fixture
def mcp_settings(tmp_path, monkeypatch):
    import agentzero.linkedin_mcp_server as limcp

    limcp._SERVICE = None
    settings = Settings(_env_file=None, db_path=tmp_path / "mcp.db")
    monkeypatch.setattr("agentzero.config.get_settings", lambda: settings)
    return settings


def test_build_server_registers_search_and_detail_tools():
    import asyncio

    server = build_server()
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert "pull_linkedin_jobs" in tools
    assert "get_job_details" in tools
    assert "check_linkedin_session" in tools
    assert "close_session" in tools
    assert "get_apply_links" in tools
    assert "record_application" in tools


def test_pull_linkedin_jobs_tool_mocked_service(mcp_settings, monkeypatch):
    import agentzero.linkedin_mcp_server as limcp

    records = [
        {
            "title": "Engineer",
            "company": "Acme",
            "url": "https://www.linkedin.com/jobs/view/1234567890",
            "source": "linkedin",
        }
    ]
    mock_result = LinkedInSearchResult(
        records=records,
        url="https://www.linkedin.com/jobs/search",
    )
    mock_service = MagicMock()
    mock_service.search.return_value = mock_result
    limcp._SERVICE = mock_service
    server = build_server()
    out = _call_tool(server, "pull_linkedin_jobs", {"persist_leads": False})
    assert out["count"] == 1
    assert len(out["job_ids"]) == 1


def test_check_linkedin_session(monkeypatch, mcp_settings):
    probe = SessionProbeResult(
        site="linkedin",
        state=SessionState.READY,
        url="https://www.linkedin.com/jobs/",
        listing_count=5,
    )
    monkeypatch.setattr(
        "agentzero.scrape.session_probe.probe_browser_session",
        lambda _s, _site: probe,
    )
    server = build_server()
    out = _call_tool(server, "check_linkedin_session")
    assert out["state"] == "ready"


def test_concurrent_tool_calls_serialize_on_shared_lock(mcp_settings, monkeypatch):
    import agentzero.linkedin_mcp_server as limcp

    acquired: list[int] = []

    class BlockingService:
        def search(self, *, progress=None):
            acquired.append(1)
            assert limcp._BROWSER_LOCK.locked()
            return LinkedInSearchResult(url="https://li/search")

    limcp._SERVICE = BlockingService()
    server = build_server()
    _call_tool(server, "pull_linkedin_jobs")
    assert acquired == [1]


def test_record_application_sets_date_applied(mcp_settings, monkeypatch):
    from agentzero.storage.db import Database

    db = Database(mcp_settings.db_path)
    job = JobPosting(
        title="Engineer",
        company="Acme",
        url="https://www.linkedin.com/jobs/view/1234567890",
        source="linkedin",
        status=ApplicationStatus.NEW,
    )
    db.upsert_job(job)
    db.close()

    server = build_server()
    out = _call_tool(
        server,
        "record_application",
        {"job_id": job.job_id, "applied_date": "2026-06-02"},
    )
    assert out["date_applied"] == "2026-06-02"
    assert out["status"] == "applied"

    db2 = Database(mcp_settings.db_path)
    stored = db2.get_job(job.job_id)
    assert stored is not None
    assert stored.date_applied == date(2026, 6, 2)
    db2.close()


def test_record_application_rejects_unknown_job_id(mcp_settings):
    server = build_server()
    out = _call_tool(server, "record_application", {"job_id": "nonexistent-id"})
    assert out["error"] == "job_not_found"


def test_main_help_exits_zero():
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "agentzero.linkedin_mcp_server", "--help"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "stdio" in (proc.stdout + proc.stderr).lower()


def test_instructions_mention_pull():
    assert "pull_linkedin_jobs" in LINKEDIN_MCP_INSTRUCTIONS
