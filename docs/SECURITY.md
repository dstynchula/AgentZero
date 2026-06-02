# Security

AgentZero runs locally on your machine, reads your résumé, calls third-party APIs, and
optionally syncs to Google Sheets. This document describes secrets, scopes, network
egress, and operator safety for self-hosted use.

## Secrets (never commit)

| File / directory | Contents |
|------------------|----------|
| `.env` | LLM API keys, sheet ID, scrape settings |
| `token.json` | Google OAuth refresh token |
| `client_secret.json` | Google OAuth client credentials |
| `data/agentzero.db` | Job listings and enrichment data |
| `data/browser_profiles/`, `data/indeed_browser_profile/` | **Logged-in job-board session cookies** |
| `resume/` | Personal résumé (gitignored) |

If any secret is committed or shared, rotate it immediately (new API key, re-run
`scripts/google_auth.py`, clear browser profiles and log in again).

## Google OAuth scopes

Production scripts today only need **Google Sheets**:

| Scope | Used by | Default? |
|-------|---------|------------|
| `spreadsheets` | `sync_sheets.py`, `rank_and_sync.py`, `enrich_jobs.py --sync` | **Yes** |
| `gmail.modify`, `calendar`, `drive.file` | Reserved for future integrations | No (`--full-scopes` only; no code paths yet) |

```powershell
python scripts/google_auth.py              # Sheets only (recommended)
python scripts/google_auth.py --full-scopes  # Only if you add Gmail/Calendar/Drive features
```

Verify the target spreadsheet before syncing:

```powershell
python scripts/sync_sheets.py --dry-run
python scripts/sync_sheets.py --yes
```

**Operator error:** `sync_sheets.py --yes` clears and rewrites the entire worksheet. Confirm
`AGENTZERO_SHEET_ID` points at your job tracker, not another document.

To drop DB rows you removed from the sheet:

```powershell
python scripts/prune_db_from_sheet.py --dry-run
python scripts/prune_db_from_sheet.py --yes
```

## LLM data processing

When LLM features are enabled, the following may be sent to OpenAI or Anthropic
(depending on `AGENTZERO_LLM_PROVIDER`):

- **Résumé plain text** — ingest and search-profile extraction
- **Job titles, descriptions, company names** — ranking and optional LLM repair of bad scrapes
- **Truncated descriptions** — rank prompts cap length via `AGENTZERO_RANK_DESCRIPTION_MAX_CHARS`

Rank prompts include résumé **name, skills, experience, summary** — not email.

Review your provider's data retention and enterprise policies before use.

### Untrusted input from job boards

Scraped listing text is **hostile input**. Job descriptions, titles, and raw scrape payloads
may contain prompt-injection patterns designed to influence LLM repair or ranking output.

Mitigations today:

- Deterministic validation and alias repair run before any LLM call
- Rank prompts truncate description length
- LLM repair output is re-validated against the `JobPosting` schema before storage
- Failed records go to quarantine instead of the main jobs table

Treat LLM-derived match scores and repaired fields as **assistive**, not authoritative.

## Network egress

| Component | Destinations |
|-----------|--------------|
| Scrape (JobSpy) | Job boards, Google Jobs, ZipRecruiter |
| Scrape (Playwright) | Indeed, LinkedIn, Glassdoor |
| Enrichment | Job posting URLs, Glassdoor, DuckDuckGo (`ddgs`), careers pages |
| LLM | Provider API |
| Google | Sheets API (when syncing) |

### SSRF protection (enrichment HTTP)

Outbound HTTP fetches in enrichment (`detail_fetch`, `web_research`, careers URL
verification) validate URLs via `agentzero.net.url_safety`:

- Only `http` / `https`
- Blocks localhost, private/link-local IPs, and cloud metadata hosts
- DNS resolution checked before fetch
- Redirect hops re-validated (max 5); unsafe redirect targets are blocked
- Response bodies capped at 2 MB by default (`safe_get_text`)

**Out of scope:** JobSpy and Playwright scrape paths intentionally navigate to job-board
URLs without the enrichment SSRF guard — that is the product's core function. Browser
navigation after `page.goto()` is checked via `validate_browser_page_url()` on board
search and session-probe paths. Detail fetch validates both the requested URL and the
post-navigation browser URL.

**Known limitation:** DNS is resolved at validation time; the HTTP client does not pin
connections to those addresses (time-of-check/time-of-use). Acceptable for local
self-hosted use; do not expose enrichment fetch to untrusted URL input from remote callers.

### CDP (Chrome DevTools Protocol)

`AGENTZERO_SCRAPE_CDP_URL` must target a **permitted local listener**:

- `127.0.0.1`, `localhost`, `::1` (default)
- `host.docker.internal` only when `AGENTZERO_CDP_ALLOW_DOCKER_HOST=true` (Docker compose path; see [DOCKER.md](DOCKER.md))

Remote CDP endpoints are rejected at config load time to prevent attaching Playwright to
an attacker-controlled browser. Auto-launch starts a dedicated profile under
`data/browser_profiles/cdp` on the host — not your daily Chrome profile. Inside Docker,
set `AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=false` and start Chrome on the host with
`scripts/launch_chrome_cdp.ps1`.

### Log redaction

`agentzero/log_redaction.py` installs a root logging filter on import (API keys, Bearer tokens,
OAuth JSON fields, proxy credentials). Script output should use `mask_sheet_id()` for sheet IDs.

This is **best-effort** for app-controlled logs. Do not run `docker compose config` or paste
`.env` into tickets. Keep log level at INFO in production compose (avoid httpx/playwright DEBUG).

### Web UI (Docker `web` service)

- **Unauthenticated** HTTP on port **8080** (default). Anyone who can reach the port can list
  and edit jobs in the mounted SQLite database (status, notes, soft-reject).
- Intended for **local operator** use only. Do not publish 8080 to the public internet.
- The web layer does **not** hard-delete rows; **Nope** sets `rejected` (same as MCP `reject_leads`).
- No Google OAuth in the web process; sheet sync remains a separate CLI step.

### Docker secrets

- Never bake `.env`, `token.json`, or `client_secret.json` into the image (see `.dockerignore`).
- Runtime secrets: `env_file: .env` and read-only bind mounts in `docker-compose.yml`.
- Do not store secrets in GitHub Actions for local Docker use; CI builds the image without `env_file`.

### OAuth token storage

`token.json` stores refresh tokens only — `client_secret` is stripped on save. Keep
`client_secret.json` gitignored separately.

On save, `persist_credentials` restricts file permissions:

- **Unix:** `chmod 0o600` (owner read/write only)
- **Windows:** `icacls` removes inherited ACLs and grants the current user full control only

## Scraping and legal use

Scraping may violate site Terms of Service. AgentZero uses rate limits, sequential
sources, and human CAPTCHA steps, but **you are responsible** for compliant use.

Applications are **never auto-submitted**. The live pipeline is scrape → enrich → rank →
sheet sync; you apply manually on each job board. Application status is tracked in the
Google Sheet and imported via `agentzero/apply/tracking.py`.

Lead-session statuses: `lead` and `rejected` stay in SQLite only until you approve (`new`)
and commit; `reject_leads` never pushes those rows to the sheet.

## MCP server

`agentzero/mcp_server.py` exposes lead-session tools over **stdio** (local trust boundary):

- Read: `scrape_status`, `list_quarantine`, `list_leads`, `suggest_targets`
- Write: `run_scrape`, `approve_leads`, `reject_leads`, `commit_leads` (sheet sync)

MCP tool inputs are bounded (max titles, results, job id count). The server ships with
**interactive workflow instructions** — the Cursor agent should confirm with you before
each scrape and sheet commit.

Project config: `.cursor/mcp.json`. Agent rules: `AGENTS.md` and `.cursor/rules/agentzero-mcp.mdc`.

Any process that can launch the MCP server can read/write local job data and trigger scrapes.
Do not expose MCP to untrusted clients.

## Browser automation

- Default `AGENTZERO_SCRAPE_BROWSER_HEADLESS=false` shows a visible browser (helps with CAPTCHA; shoulder-surfing risk on shared machines).
- Persistent profiles live under `data/browser_profiles/` and legacy `data/indeed_browser_profile/`.
- `data/browser_storage_state/` holds imported cookie exports — treat like passwords.

## Reporting issues

For security concerns in this repo, open a private issue or contact the maintainer
directly rather than posting exploit details publicly.
