"""Interactive lead-session workflow text for MCP-driven Cursor chat."""

from __future__ import annotations

LEAD_SESSION_WORKFLOW: list[dict[str, str]] = [
    {
        "step": "1",
        "action": "suggest_targets",
        "prompt_user": (
            "Present suggested job titles, locations, remote-only, and comp floor. "
            "Ask the user to confirm or edit before scraping."
        ),
    },
    {
        "step": "2",
        "action": "check_sessions",
        "prompt_user": (
            "Probe Indeed/LinkedIn/Glassdoor sessions. If login or CAPTCHA is required, "
            "tell the user to complete it in the Chrome window (CDP auto-starts when needed)."
        ),
    },
    {
        "step": "3",
        "action": "run_scrape",
        "prompt_user": (
            "Only after explicit user confirmation of titles/comp/remote settings. "
            "New roles land as lead in SQLite — review before promoting."
        ),
    },
    {
        "step": "4",
        "action": "list_leads",
        "prompt_user": (
            "Show the scored preview table. Ask which roles to approve, reject, or skip."
        ),
    },
    {
        "step": "5",
        "action": "commit_leads",
        "prompt_user": (
            "After user picks job_ids, approve leads (LEAD → NEW in SQLite). "
            "Point them to the web UI at http://localhost:8080 for day-to-day tracking."
        ),
    },
]

MCP_SERVER_INSTRUCTIONS = """\
AgentZero MCP — interactive lead-gathering assistant.

Always run the lead session as a conversational flow in chat. Never skip user confirmation.

Workflow (in order):
1. suggest_targets — show résumé-derived titles/locations/comp; wait for user edits.
2. check_sessions — verify browser logins; CDP Chrome auto-launches when configured and not running.
3. run_scrape — only after user confirms search parameters.
4. Present list_leads / run_scrape preview; discuss fit with the user.
5. approve_leads or commit_leads — only for job_ids the user explicitly selects.

Rules:
- Treat MCP as a chat copilot, not a silent batch job.
- Ask before every scrape and before promoting leads.
- reject_leads keeps rows in SQLite for dedupe but hides them in the default web UI.
- commit_leads promotes LEAD → NEW in SQLite only (no external sheet sync).
- Track applications in the local web UI: docker compose up web → http://localhost:8080
- If check_sessions reports login_required or blocked, pause and guide the user (login_job_boards / CAPTCHA).
- Use lead_session_workflow() when the user asks to gather leads or start a job search session.
"""


def lead_session_workflow_text() -> str:
    """Human-readable workflow for the Cursor agent."""
    lines = [
        "# AgentZero interactive lead session",
        "",
        "Run these MCP tools **in chat**, confirming with the user between steps:",
        "",
    ]
    for item in LEAD_SESSION_WORKFLOW:
        lines.append(f"{item['step']}. **{item['action']}** — {item['prompt_user']}")
    lines.extend(
        [
            "",
            "Supporting tools: scrape_status, list_leads, approve_leads, reject_leads, list_quarantine.",
            "Web tracker: docker compose up web → http://localhost:8080",
            "Chrome CDP auto-starts when AGENTZERO_SCRAPE_CDP_URL is set and Chrome was closed.",
        ]
    )
    return "\n".join(lines)
