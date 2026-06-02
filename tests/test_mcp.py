"""Tests for agentzero.mcp_server (tool registration, schemas, mocked handlers)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastmcp.exceptions import ToolError

from agentzero.config import Settings
from agentzero.ingest.search_profile import ResumeSearchProfile
from agentzero.leads.session import LeadRunResult, SearchTargets
from agentzero.loops.pipeline import PipelineResult
from agentzero.mcp_server import build_server, main
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.scrape.browser_session import SessionState
from agentzero.scrape.session_probe import SessionProbeResult
from agentzero.storage.db import Database

EXPECTED_TOOLS = {
    "lead_session_workflow",
    "scrape_status",
    "list_quarantine",
    "suggest_targets",
    "check_sessions",
    "run_scrape",
    "list_leads",
    "approve_leads",
    "reject_leads",
    "commit_leads",
}


def _run(coro):
    return asyncio.run(coro)


async def _call_tool(mcp, name: str, arguments: dict | None = None):
    result = await mcp.call_tool(name, arguments or {})
    content = result.structured_content
    if isinstance(content, dict) and set(content.keys()) == {"result"}:
        return content["result"]
    return content


def _sample_profile(resume_path: Path = Path("resume/test.docx")) -> ResumeSearchProfile:
    return ResumeSearchProfile(
        search_terms=["Staff Security Engineer"],
        locations=["Remote, USA"],
        remote_preferred=True,
        salary_min=180_000.0,
        source_resume_path=str(resume_path),
        source_fingerprint="abc123",
        updated_at="2026-01-01T00:00:00Z",
    )


def _job(**kwargs) -> JobPosting:
    base = dict(
        title="Security Engineer",
        company="Acme",
        url="https://example.com/job/1",
        source="indeed",
        date_posted=date.today(),
    )
    base.update(kwargs)
    return JobPosting(**base)


@pytest.fixture
def mcp_settings(tmp_path) -> Settings:
    return Settings(_env_file=None, db_path=tmp_path / "mcp.db")


@pytest.fixture
def mcp_server(mcp_settings, monkeypatch):
    monkeypatch.setattr("agentzero.config.get_settings", lambda: mcp_settings)
    return build_server()


def test_mcp_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "agentzero.mcp_server", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "AgentZero MCP server" in result.stdout


def test_mcp_main_requires_stdio():
    result = subprocess.run(
        [sys.executable, "-m", "agentzero.mcp_server"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "stdio" in (result.stderr + result.stdout).lower()


def test_build_server_requires_fastmcp(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fastmcp":
            raise ImportError("blocked")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match=r"pip install -e '\.\[mcp\]'"):
        build_server()


def test_build_server_registers_expected_tools(mcp_server):
    tools = _run(mcp_server.list_tools())
    names = {tool.name for tool in tools}
    assert names == EXPECTED_TOOLS


def test_tool_schemas_expose_required_arguments(mcp_server):
    tools = {tool.name: tool for tool in _run(mcp_server.list_tools())}

    run_scrape = tools["run_scrape"]
    assert "search_terms" in run_scrape.parameters["properties"]
    assert "search_terms" in run_scrape.parameters["required"]

    for name in ("approve_leads", "reject_leads", "commit_leads"):
        schema = tools[name].parameters
        assert "job_ids" in schema["properties"]
        assert schema["properties"]["job_ids"]["type"] == "array"
        assert "job_ids" in schema["required"]

    suggest = tools["suggest_targets"]
    assert suggest.parameters["properties"]["force_refresh"]["default"] is False


def test_lead_session_workflow_tool(mcp_server):
    text = _run(_call_tool(mcp_server, "lead_session_workflow"))
    assert "suggest_targets" in text
    assert "commit_leads" in text


def test_scrape_status_counts_jobs(mcp_server, mcp_settings):
    db = Database(mcp_settings.db_path)
    db.upsert_job(_job(status=ApplicationStatus.LEAD))
    db.close()

    payload = _run(_call_tool(mcp_server, "scrape_status"))
    assert payload["jobs"] == 1
    assert payload["pending_leads"] == 1


def test_list_quarantine_empty(mcp_server):
    rows = _run(_call_tool(mcp_server, "list_quarantine"))
    assert rows == []


def test_list_leads_pending_only(mcp_server, mcp_settings):
    db = Database(mcp_settings.db_path)
    db.upsert_job(_job(status=ApplicationStatus.LEAD, url="https://example.com/a"))
    db.upsert_job(_job(status=ApplicationStatus.NEW, url="https://example.com/b"))
    db.close()

    leads = _run(_call_tool(mcp_server, "list_leads"))
    assert len(leads) == 1
    assert leads[0]["status"] == ApplicationStatus.LEAD.value


def test_suggest_targets_handler(monkeypatch, mcp_settings):
    profile = _sample_profile()
    targets = SearchTargets(
        search_terms=["Staff Engineer"],
        locations=["Remote"],
        remote_preferred=True,
        salary_min=150_000.0,
        candidate_name="Test User",
        profile=profile,
    )
    monkeypatch.setattr("agentzero.config.get_settings", lambda: mcp_settings)
    monkeypatch.setattr("agentzero.llm.provider.build_llm_provider", lambda: MagicMock())
    monkeypatch.setattr(
        "agentzero.leads.session.suggest_targets",
        lambda llm, force_refresh=False: targets,
    )
    server = build_server()

    payload = _run(_call_tool(server, "suggest_targets", {"force_refresh": True}))
    assert payload["candidate_name"] == "Test User"
    assert payload["search_terms"] == ["Staff Engineer"]
    assert payload["remote_preferred"] is True
    assert payload["salary_min"] == 150_000.0
    assert "next_step" in payload


def test_check_sessions_maps_probe_results(monkeypatch, mcp_settings):
    @dataclass
    class PlainState:
        value: str

    probes = [
        SessionProbeResult(
            site="indeed",
            state=SessionState.READY,
            url="https://indeed.com",
            listing_count=3,
        ),
        SessionProbeResult(
            site="legacy",
            state=PlainState("legacy"),  # type: ignore[arg-type]
            url="https://legacy.example",
            listing_count=0,
            error="timeout",
        ),
    ]
    monkeypatch.setattr("agentzero.config.get_settings", lambda: mcp_settings)
    monkeypatch.setattr("agentzero.scrape.browser_common.ensure_cdp_for_sites", lambda settings: None)
    monkeypatch.setattr("agentzero.leads.session.check_board_sessions", lambda settings: probes)
    server = build_server()

    rows = _run(_call_tool(server, "check_sessions"))
    assert len(rows) == 2
    assert rows[0]["site"] == "indeed"
    assert rows[0]["state"] == "ready"
    assert rows[0]["ready"] is True
    assert rows[0]["listing_count"] == 3
    assert rows[1]["state"] == "legacy"
    assert rows[1]["ready"] is False
    assert rows[1]["error"] == "timeout"


def test_run_scrape_rejects_empty_search_terms(mcp_server):
    with pytest.raises(ToolError, match="search_terms must contain"):
        _run(_call_tool(mcp_server, "run_scrape", {"search_terms": []}))


def test_run_scrape_handler_mocked(monkeypatch, mcp_settings):
    profile = _sample_profile()
    targets = SearchTargets(
        search_terms=["Staff Engineer"],
        locations=["Remote"],
        remote_preferred=True,
        salary_min=None,
        candidate_name=None,
        profile=profile,
    )
    lead = _job(status=ApplicationStatus.LEAD, url="https://example.com/new")
    run_result = LeadRunResult(
        pipeline=PipelineResult(scraped=2, ranked=1, quarantined=0, errors=[]),
        leads=[lead],
    )

    monkeypatch.setattr("agentzero.config.get_settings", lambda: mcp_settings)
    monkeypatch.setattr("agentzero.scrape.browser_common.ensure_cdp_for_sites", lambda settings: None)
    monkeypatch.setattr("agentzero.llm.provider.build_llm_provider", lambda: MagicMock())
    monkeypatch.setattr(
        "agentzero.leads.session.suggest_targets",
        lambda llm, force_refresh=False: targets,
    )
    monkeypatch.setattr("agentzero.ingest.resume.ingest_resume", lambda **kwargs: MagicMock())
    monkeypatch.setattr("agentzero.leads.session.run_lead_scrape", lambda db, effective, llm, profile: run_result)
    server = build_server()

    payload = _run(
        _call_tool(
            server,
            "run_scrape",
            {"search_terms": ["  Staff Engineer  "], "remote_only": False, "salary_min": 120000},
        )
    )
    assert payload["scraped"] == 2
    assert payload["lead_count"] == 1
    assert len(payload["leads"]) == 1
    assert payload["leads"][0]["job_id"] == lead.job_id
    assert "preview" in payload


def test_approve_and_reject_leads_handlers(mcp_server, mcp_settings):
    db = Database(mcp_settings.db_path)
    lead = _job(status=ApplicationStatus.LEAD, url="https://example.com/lead")
    db.upsert_job(lead)
    db.close()

    approved = _run(_call_tool(mcp_server, "approve_leads", {"job_ids": [lead.job_id, lead.job_id]}))
    assert approved["approved"] == 1
    assert approved["requested"] == 1

    db = Database(mcp_settings.db_path)
    lead2 = _job(status=ApplicationStatus.LEAD, url="https://example.com/lead2")
    db.upsert_job(lead2)
    db.close()

    rejected = _run(_call_tool(mcp_server, "reject_leads", {"job_ids": [lead2.job_id]}))
    assert rejected["rejected"] == 1


def test_commit_leads_handler_mocked(monkeypatch, mcp_settings):
    db = Database(mcp_settings.db_path)
    lead = _job(status=ApplicationStatus.LEAD, url="https://example.com/commit")
    db.upsert_job(lead)
    db.close()

    monkeypatch.setattr("agentzero.config.get_settings", lambda: mcp_settings)
    server = build_server()

    payload = _run(_call_tool(server, "commit_leads", {"job_ids": [lead.job_id]}))
    assert payload["approved"] == 1
    assert "tracker_note" in payload


def test_job_id_validation_surfaces_as_tool_error(mcp_server):
    with pytest.raises(ToolError, match="job_ids must not be empty"):
        _run(_call_tool(mcp_server, "commit_leads", {"job_ids": []}))


def test_main_stdio_runs_server(monkeypatch):
    ran: list[str] = []

    class FakeServer:
        def run(self) -> None:
            ran.append("run")

    monkeypatch.setattr("agentzero.mcp_server.build_server", lambda: FakeServer())
    monkeypatch.setattr(sys, "argv", ["agentzero.mcp_server", "--stdio"])
    main()
    assert ran == ["run"]
