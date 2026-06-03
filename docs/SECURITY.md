# Security

AgentZero runs locally on your machine, reads your résumé, and calls third-party APIs.
Job tracking uses **SQLite** and the optional **web UI** on port 8080. This document
describes secrets, network egress, and operator safety for self-hosted use.

## Secrets (never commit)

| File / directory | Contents |
|------------------|----------|
| `.env` | LLM API keys, scrape settings |
| `data/agentzero.db` | Job listings and enrichment data |
| `data/browser_profiles/`, `data/indeed_browser_profile/` | **Logged-in job-board session cookies** |
| `resume/` | Personal résumé (gitignored) |

If any secret is committed or shared, rotate it immediately (new API key, clear browser
profiles and log in again).

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
`scripts/launch_chrome_cdp.ps1`, `scripts/launch_chrome_cdp.py`, or `scripts/launch_chrome_cdp.sh`.

### Log redaction

`agentzero/log_redaction.py` installs a root logging filter on import (API keys, Bearer tokens,
OAuth JSON fields, proxy credentials).

This is **best-effort** for app-controlled logs. Do not run `docker compose config` or paste
`.env` into tickets. Keep log level at INFO in production compose (avoid httpx/playwright DEBUG).

### Web UI (Docker `web` service)

- **Unauthenticated** HTTP on port **8080** (default). Anyone who can reach the port can list
  and edit jobs in the mounted SQLite database (status, notes, soft-reject).
- **Chat** (`/`) calls OpenAI with job/résumé context when you send messages (`AGENTZERO_CHAT_MODEL`).
  Mutating tool calls (scrape, status, cover letter, leads) execute only after you click **Confirm**.
- Intended for **local operator** use only. Do not publish 8080 to the public internet.
- The web layer does **not** hard-delete rows; **Nope** sets `rejected` (same as MCP `reject_leads`).
- **Scraper** search-targets form inputs (work mode, locations, comp floor) are validated server-side
  (bounded strings, no control characters, capped list size and salary range) before persisting to
  `data/web_operator_config.json`. They are not passed to LLM prompts except indirectly via scrape.
### Docker secrets

- Never bake `.env` into the image (see `.dockerignore`).
- Runtime secrets: `env_file: .env` in `docker-compose.yml`.
- Do not store secrets in GitHub Actions for local Docker use; CI builds the image without `env_file`.

## Scraping and legal use

Scraping may violate site Terms of Service. AgentZero uses rate limits, sequential
sources, and human CAPTCHA steps, but **you are responsible** for compliant use.

Applications are **never auto-submitted**. The live pipeline is scrape → enrich → rank;
you apply manually on each job board. Application status is tracked in SQLite and the web UI.

Lead-session statuses: `lead` and `rejected` stay hidden from the default web view until you
approve (`new`) via MCP or the UI.

## MCP server

`agentzero/mcp_server.py` exposes lead-session tools over **stdio** (local trust boundary):

- Read: `scrape_status`, `list_quarantine`, `list_leads`, `suggest_targets`
- Write: `run_scrape`, `approve_leads`, `reject_leads`, `commit_leads` (SQLite promote only)

MCP tool inputs are bounded (max titles, results, job id count). The server ships with
**interactive workflow instructions** — the Cursor agent should confirm with you before
each scrape and lead commit.

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
