# P31 — Remove Google Sheets; local web UI is the tracker

## Mission

Drop all Google Sheets OAuth, sync scripts, and `agentzero/google/`. Operators track jobs in
SQLite and the Docker web UI on port 8080 (`docker compose up web`).

## Locked decisions

- No Google OAuth / gspread / Sheets API in tree or Docker image `[google]` extra.
- `commit_leads` approves leads in DB only (no sheet push).
- `SHEET_COLUMNS` → `TRACKER_UI_COLUMNS` (web table); CSV export unchanged.
- Keep `apply/tracker_fields.py` + `tracking.py` for row-merge helpers (used by web mutations).

## Task ledger

- [x] P31a Remove `agentzero/google/`, sheet scripts, config fields
- [x] P31b Leads/MCP/scripts — approve-only commit; `rank_jobs.py` replaces sync CLI
- [x] P31c Rename tracker columns; update web imports
- [x] P31d Docs, compose, Dockerfile, `.env.example`, AGENTS.md
- [x] P31e Tests + PROGRESS ledger

## Acceptance

`ruff check agentzero tests scripts tools && pytest --cov=agentzero --cov-branch -q`
