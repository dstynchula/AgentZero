"""Tests for MCP lead-session workflow helpers."""

from agentzero.mcp.workflow import (
    LEAD_SESSION_WORKFLOW,
    MCP_SERVER_INSTRUCTIONS,
    lead_session_workflow_text,
)


def test_lead_session_workflow_text_includes_all_steps():
    text = lead_session_workflow_text()
    for item in LEAD_SESSION_WORKFLOW:
        assert item["action"] in text
        assert item["prompt_user"] in text
        assert f"{item['step']}. **{item['action']}**" in text


def test_lead_session_workflow_text_includes_supporting_tools():
    text = lead_session_workflow_text()
    assert "Supporting tools:" in text
    assert "scrape_status" in text
    assert "Chrome CDP auto-starts" in text


def test_lead_session_workflow_text_starts_with_header():
    text = lead_session_workflow_text()
    assert text.startswith("# AgentZero interactive lead session")


def test_mcp_server_instructions_cover_key_rules():
    assert "suggest_targets" in MCP_SERVER_INSTRUCTIONS
    assert "commit_leads" in MCP_SERVER_INSTRUCTIONS
    assert "Never skip user confirmation" in MCP_SERVER_INSTRUCTIONS
