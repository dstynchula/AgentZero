# AgentZero — Cursor agent instructions

When the **AgentZero MCP server** is enabled, treat every job-search request as an
**interactive chat session**. Do not run scrape or sheet-commit tools silently.

## Lead session workflow

1. Call **`lead_session_workflow`** (or follow the steps below).
2. **`suggest_targets`** — show titles, locations, remote-only, comp floor; **wait for user confirmation**.
3. **`check_sessions`** — verify board logins. CDP Chrome auto-starts when configured and not running.
4. **`run_scrape`** — only after the user confirms search parameters.
5. Present the preview table; discuss fit; ask which roles to keep.
6. **`commit_leads`** — only for `job_id`s the user explicitly selects.

## Rules

- Ask before every scrape and before every Google Sheet commit.
- If `check_sessions` reports login required or blocked, pause and guide the user
  (`login_job_boards.py`, CAPTCHA in the Chrome window).
- Report actual `approved` counts from `commit_leads`, not the number of ids requested.
- Prefer **`run_lead_session.py`** in terminal when the user wants a local wizard; use MCP
  tools when driving the session from chat.

## Chrome / CDP

Indeed and Glassdoor use CDP when `AGENTZERO_SCRAPE_CDP_URL` is set. AgentZero **auto-launches**
dedicated Chrome when the endpoint is down (`AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=true`, default).
LinkedIn uses a separate Playwright profile unless CDP is configured for it.

See [docs/SCRAPING.md](docs/SCRAPING.md) and [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).
