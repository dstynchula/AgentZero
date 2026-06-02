# Scraping, OAuth, and first live run

**Last updated: 2026-05-31**

AgentZero sources jobs through **Playwright (real browser)** and **JobSpy (HTTP/TLS)**.
Boards aggressively rate-limit automated traffic (HTTP 400/429). This document describes
the architecture, configuration, scripts, and known limitations.

## Architecture

```
résumé → LLM search profile → user confirms titles/locations/salary → scrape sources → …
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        ▼                                                       ▼
 BrowserJobBoardSource (Playwright)                      JobSpySource (HTTP)
  indeed → linkedin → glassdoor                          google → zip_recruiter
        (sequential, delay between each)                  (one primary query each)
```

| Component | File | Role |
|-----------|------|------|
| Source factory | `agentzero/scrape/factory.py` | Fixed five-source stack; no JSON merge |
| Browser boards | `agentzero/scrape/browser_board.py` | Indeed, LinkedIn, Glassdoor (one query each) |
| Title filter | `agentzero/scrape/title_filter.py` | Drop off-topic titles at scrape |
| Remote policy | `agentzero/scrape/remote_policy.py` | Remote-only queries + post-scrape filter |
| LinkedIn parser | `agentzero/scrape/browser_linkedin.py` | Legacy cards + SPA DOM + embedded Voyager JSON |
| Glassdoor employer | `agentzero/scrape/glassdoor_company.py` | Resolve `Unknown` from URL slugs, JSON, description |
| Export filter | `agentzero/rank/export_filter.py` | Min match score for Sheet/CSV |
| Application tracking | `agentzero/apply/tracking.py` | Sheet ↔ DB for applied jobs |
| Browser helpers | `agentzero/scrape/browser_common.py` | CAPTCHA wait (max 3 prompts), primary query |
| JobSpy wrapper | `agentzero/scrape/jobspy_source.py` | Google + ZipRecruiter only; sequential with delay |
| Multi-source | `agentzero/scrape/multi.py` | Runs sources in factory order |
| Resilience | `agentzero/scrape/resilience.py` | Default UA, core JobSpy site list |
| Search prompt | `agentzero/ingest/search_interactive.py` | Per-run titles/locations/salary |

## Interactive search targeting

Before each scrape, AgentZero shows résumé-derived suggestions and asks you to confirm or edit:

- **Job titles** — comma-separated (e.g. `Staff Security Engineer, Principal Security Engineer`)
- **Locations** — comma-separated (e.g. `Remote, Los Angeles, CA`)
- **Comp floor** — minimum acceptable USD/year; listings kept when posted range top meets or exceeds this (optional)

Press **Enter** to keep a default; type **n** at the final prompt to cancel the run.

## Enrichment and backfill

After scrape, shallow enrich runs in the pipeline (comp/size/Glassdoor from fields already on the job).
**Deep enrich** (`enrich_jobs.py`) fetches posting URLs, looks up Glassdoor, and runs DuckDuckGo company research.

| Gap | How it is filled |
|-----|------------------|
| LinkedIn comp missing | Search-card `formattedSalary` when present; else LinkedIn detail page via browser (CDP) |
| Glassdoor `Unknown` company | `glassdoor_company.py` — URL slug, embedded JSON, description patterns |
| Glassdoor rating/reviews | Direct Glassdoor HTTP (often blocked) → **DuckDuckGo web search** fallback in `enrich_jobs.py` |
| Careers URL / company size | DuckDuckGo + optional careers-page verification |

**Backfill scripts** (one-off repair on existing DB rows):

```powershell
python scripts/backfill_linkedin_comp.py          # fetch comp from LinkedIn detail pages + sync
python scripts/backfill_glassdoor_companies.py    # resolve Unknown Glassdoor employers + sync
python scripts/run_linkedin_lead_scrape.py        # LinkedIn-only lead scrape (requires CDP Chrome)
```

Re-run Glassdoor ratings after fixing company names: clear is not needed — run `enrich_jobs.py` (web search
fills missing `glassdoor_rating`/`glassdoor_reviews`). Direct Glassdoor HTTP refresh alone often fails without
a browser session; prefer `enrich_jobs.py` over ad-hoc HTTP scripts.

| Control | How |
|---------|-----|
| Default (on) | `AGENTZERO_SEARCH_INTERACTIVE=true` |
| Skip prompt | `AGENTZERO_SEARCH_INTERACTIVE=false` or `python scripts/smoke_test.py --scrape --no-search-prompt` |
| Snapshot | Saved to `resume/search_profile.json` after you confirm |

## Remote-only mode (default)

When `AGENTZERO_REMOTE_ONLY=true` (default):

1. **Scrape queries** use `remote - usa` with board remote filters (Indeed `remotejob=1`, LinkedIn `f_WT=2`, etc.) — résumé-inferred office cities are ignored.
2. **Post-scrape filter** drops listings that are on-site, hybrid, or have a city/state location without a remote signal.
3. **Interactive prompt** skips the in-office path; work mode is fixed to Remote (USA).

To search specific office cities, set `AGENTZERO_REMOTE_ONLY=false`.

Purge existing on-site rows from SQLite (applied jobs are skipped):

```powershell
python scripts/purge_non_remote_jobs.py --dry-run
python scripts/purge_non_remote_jobs.py --yes --sync-sheet
```

## Quality filters

Listings pass through several gates before they appear in the web tracker / CSV export.

### Title relevance (scrape)

After validation, jobs must match `AGENTZERO_SEARCH_TERMS` (e.g. `staff security engineer`
→ title must contain **security**). Obvious mismatches (marketing, HR, sales) are
hard-rejected. Implemented in `agentzero/scrape/title_filter.py`; browser boards also
filter at parse time.

### Remote (scrape)

See [Remote-only mode](#remote-only-mode-default). Applied jobs with `date_applied` set
are never purged by `purge_non_remote_jobs.py`.

### Match score (export)

After ranking, only jobs with `match_score >= AGENTZERO_MIN_MATCH_SCORE` (default **0.75**)
are written to the sheet or CSV export. Exceptions:

- **Applied jobs** (`date_applied` or status applied/rejected/offer) always export
- **Unranked jobs** export until scored (so new scrapes appear before you run rank)

Set `AGENTZERO_MIN_MATCH_SCORE=0` to disable. Implemented in `agentzero/rank/export_filter.py`.

Jobs with `status=lead` are **never** exported — they await operator approval first.

## Lead-gathering session

Interactive flow for scrape → review → commit:

```powershell
python scripts/run_lead_session.py
python scripts/run_lead_session.py --titles "Staff Security Engineer" --all-titles
python scripts/run_lead_session.py --yes   # approve + sync all new leads
```

1. Reads résumé, suggests titles/locations/comp
2. Prompts for your targets (or pass `--titles`, `--min-comp`, `--remote-only`)
3. Checks browser sessions (Indeed/LinkedIn/Glassdoor)
4. Scrapes + ranks; **new roles land as `lead` in SQLite** (not on the sheet)
5. Shows a scored preview; approve (`all` / job IDs) → promotes to `new` in SQLite (web UI for tracking)

**Cursor MCP:** register `python -m agentzero.mcp_server --stdio`. Tools: `suggest_targets`,
`check_sessions`, `run_scrape`, `list_leads`, `approve_leads`, `commit_leads`. Same core:
`agentzero/leads/session.py`.

## Application tracking

Human-edited sheet columns are authoritative for application state:

| Column | Purpose |
|--------|---------|
| `date_applied` | When you applied; auto-sets `status=applied` when status is blank |
| `status` | `lead`, `new`, `applied`, `rejected`, `offer`, … |
| `notes` | Free text |

The web tracker shows **13 columns** (`TRACKER_UI_COLUMNS` in `csv_export.py`). Internal /
sparse fields (`remote`, `careers_url`, `date_posted`, `match_tier`, etc.) remain in SQLite
and in full CSV export (`EXPORT_COLUMNS`).

Edit **`date_applied`**, **`status`**, and **`notes`** in the web UI (`docker compose up web`).
Scraped fields (comp, match score, etc.) remain DB-authoritative.

Code: `agentzero/apply/tracking.py`, `agentzero/apply/tracker_fields.py`, `agentzero/web/`.

## Why we got 400/429

The original JobSpy integration called **five boards concurrently** on every query.
LinkedIn, Glassdoor, and ZipRecruiter block residential IPs quickly. Indeed often
requires a **real browser** (consent banners, CAPTCHA).

### Mitigations (2026-05-29)

1. **Five core sources only** — Indeed, LinkedIn, Glassdoor (Playwright); Google + ZipRecruiter (JobSpy)
2. **Sequential order with delay** — `AGENTZERO_SCRAPE_DELAY_SECONDS` between each fetch (no concurrent boards)
3. **Single primary query** — `AGENTZERO_SCRAPE_PRIMARY_QUERY_ONLY=true` (one title per run, not 5×N sites)
4. **CAPTCHA cap** — max 3 human prompts; exits when job listings are visible
5. **Chrome user-agent** — passed to JobSpy; Playwright uses realistic viewport/locale
6. **Visible browser option** — `AGENTZERO_SCRAPE_BROWSER_HEADLESS=false` for Indeed consent/CAPTCHA
7. **SQLite lock** — parallel enrich workers no longer corrupt the DB connection

## Configuration (`.env`)

```env
# Browser boards (Playwright) — fixed order: indeed, linkedin, glassdoor
AGENTZERO_SCRAPE_BROWSER_SITES=indeed,linkedin,glassdoor

# JobSpy boards (HTTP only) — google and zip_recruiter
AGENTZERO_SCRAPE_SITES=google,zip_recruiter

# One primary title per run (recommended)
AGENTZERO_SCRAPE_PRIMARY_QUERY_ONLY=true

# Seconds between each fetch (browser board or JobSpy site)
AGENTZERO_SCRAPE_DELAY_SECONDS=3

# false = visible browser window (Chrome recommended — see GETTING_STARTED.md)
AGENTZERO_SCRAPE_BROWSER_HEADLESS=false

# Use installed Google Chrome (recommended for CAPTCHA — not bundled Chromium)
AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome

# Optional: attach to Chrome started with --remote-debugging-port=9222
# AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:9222

# Optional residential/datacenter proxies for JobSpy (ZipRecruiter may 403 without)
AGENTZERO_PROXIES=

# Minimum match_score for Sheet/CSV export (applied jobs always export). 0 = disable.
AGENTZERO_MIN_MATCH_SCORE=0.75

# Web tracker (optional): docker compose up web → http://localhost:8080
```

Per run (primary-query mode): **5 fetches** — Indeed → LinkedIn → Glassdoor → Google → ZipRecruiter.

See also: [Cost and model selection](COST_AND_MODELS.md) for LLM pricing (`gpt-5-nano` default).

## `docs/examples/job_sources.json` (reference only)

**Not loaded by `run_scrape.py`.** The live stack is in [`agentzero/scrape/factory.py`](../agentzero/scrape/factory.py)
and configured via `.env` (`AGENTZERO_SCRAPE_BROWSER_SITES`, `AGENTZERO_SCRAPE_SITES`). The JSON file
documents the five core sources; empty `job_sources` is reserved for future custom boards via
[`sources_config.py`](../agentzero/scrape/sources_config.py).

See also: **[GETTING_STARTED.md](GETTING_STARTED.md)** for install and Chrome setup.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/open_indeed_browser.py` | Open visible Chrome to pass Indeed CAPTCHA once (saves cookies) |
| `scripts/login_job_boards.py` | Log in to Indeed / LinkedIn / Glassdoor (cookies saved per site) |
| `scripts/rank_jobs.py` | LLM rank vs résumé (respects min match score for CSV export) |
| `scripts/enrich_jobs.py` | Secondary pass: job detail URLs + comp / company size / Glassdoor |
| `scripts/run_lead_session.py` | Interactive lead session: scrape → review → approve → sheet (`--all-titles`, `--yes`) |
| `scripts/run_linkedin_lead_scrape.py` | LinkedIn-only lead scrape via CDP Chrome (no interactive wizard) |
| `scripts/backfill_linkedin_comp.py` | Backfill missing LinkedIn comp from detail pages + optional sheet sync |
| `scripts/backfill_glassdoor_companies.py` | Resolve Glassdoor `Unknown` employers + optional sheet sync |
| `scripts/run_scrape.py` | Full scrape pipeline; interactive search targeting; `--skip-resume-ingest` for repeat runs |
| `scripts/import_sheet_status.py` | Import `date_applied`/status only; restore applied rows from sheet (`--sync`) |
| `scripts/purge_non_remote_jobs.py` | Delete non-remote jobs from DB; skips applied (`--yes`, `--sync-sheet`) |
| `scripts/prune_db_from_sheet.py` | Delete DB rows not in the sheet (`--dry-run`, `--yes`) |
| `scripts/smoke_test.py` | Résumé ingest + optional `--scrape --limit N` pipeline test |
| `scripts/estimate_cost.py` | LLM cost estimate from current `.env` |
| `scripts/import_browser_cookies.py` | Import Cookie-Editor export → per-site storage state |
| `scripts/cdp_browser_spike.py` | Compare bundled Chromium vs CDP-attached Chrome |
| `scripts/verify_browser_session.py` | Check profile ready before scrape (exit 0/1/2) |
| `scripts/open_glassdoor_browser.py` | Warm up Glassdoor profile (CAPTCHA/login) |

### Recommended browser session setup (repeatable daily loop)

```powershell
# .env — use real Chrome binary
AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome

# One-time or when cookies expire
python scripts/login_job_boards.py --site glassdoor,linkedin
python scripts/verify_browser_session.py --site glassdoor,linkedin

# Optional Glassdoor boost: export cookies from daily Chrome
python scripts/import_browser_cookies.py --site glassdoor --from cookies.json

# Daily scrape
python scripts/run_scrape.py --limit 10
```

**Cursor IDE browser** is separate from Playwright — it cannot export cookies into AgentZero (MCP blocks cookie CDP). Use the scripts above, not the IDE browser tab, for scrape sessions.

### Recommended first-run sequence

```powershell
pip install -e ".[dev,scrape,llm,mcp,web]"
playwright install chrome
copy .env.example .env          # OPENAI_API_KEY + AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome
python scripts/login_job_boards.py --site linkedin,glassdoor
python scripts/verify_browser_session.py --site linkedin
python scripts/run_scrape.py --limit 5
docker compose up web           # optional tracker
```

When Chrome opens, complete **cookie consent** or **CAPTCHA**, then continue in the terminal if prompted.

### Indeed CAPTCHA (visible browser)

Your `.env` should include:

```env
AGENTZERO_SCRAPE_BROWSER_HEADLESS=false
AGENTZERO_SCRAPE_BROWSER_PAUSE_FOR_CAPTCHA=true
```

**Option A — warm up once, then scrape:**

```powershell
python scripts/open_indeed_browser.py
python scripts/run_scrape.py --limit 25
```

**Option B — scrape directly:** `run_scrape.py` opens Chromium, waits for Indeed's embedded job JSON to load, and only pauses if a real block/CAPTCHA page appears (not when listings are already visible).

Indeed injects listings as JSON (`window.mosaic.providerData["mosaic-provider-jobcards"]`). AgentZero reads that first — not fragile CSS classes like `job_seen_beacon`.

## Browser session integration (Chrome profile, cookies, CDP)

AgentZero scrape browsers are **Playwright**, not the Cursor IDE embedded browser. The IDE browser MCP cannot export cookies into AgentZero (CDP cookie commands are blocked for security).

### Real Chrome instead of bundled Chromium

Use your installed Chrome binary for better TLS/stack alignment (helps vs Cloudflare):

```env
AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome
```

Requires Google Chrome installed. Profiles still live under `data/browser_profiles/<site>/`.

### Import cookies from your daily browser

1. In Chrome/Edge, log in to Glassdoor (or LinkedIn / Indeed).
2. Export cookies with a **Cookie-Editor** extension (JSON array) or Playwright `storage_state`.
3. Import:

```powershell
python scripts/import_browser_cookies.py --site glassdoor --from C:\path\to\cookies.json
python scripts/import_browser_cookies.py --site glassdoor --from cookies.json --apply
```

Files are saved to `data/browser_storage_state/<site>.json` (gitignored). Every scrape run loads them into the Playwright profile automatically.

### CDP attach (strongest session, interactive only)

AgentZero **auto-launches** dedicated CDP Chrome when `AGENTZERO_SCRAPE_CDP_URL` is set,
the endpoint is down, and `AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=true` (default). Manual start:

Start dedicated CDP Chrome from the repo root:

| Platform | Command |
|----------|---------|
| Windows (PowerShell) | `.\scripts\launch_chrome_cdp.ps1` |
| macOS / Linux | `python scripts/launch_chrome_cdp.py` |
| macOS / Linux (shell) | `./scripts/launch_chrome_cdp.sh` |

Set in `.env`:

```env
AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:9222
AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=true
```

CDP URLs must be **localhost only** (security guard). Profile: `data/browser_profiles/cdp`.

Legacy manual attach to your daily Chrome profile (not recommended on Chrome 136+):

```powershell
python scripts/cdp_browser_spike.py --site glassdoor --compare
```

**Security:** CDP exposes your browser to localhost — never bind `0.0.0.0`. AgentZero disconnects without closing your Chrome window when CDP mode is active.

### Cursor IDE browser

Use the IDE browser for agent-assisted debugging only. For production scrapes, use `login_job_boards.py`, cookie import, or CDP attach above.

## Résumé-driven search

On each scrape run with an LLM configured:

1. Latest file in `resume/` is read
2. LLM extracts search terms (recent job titles first) and locations
3. Snapshot saved to `resume/search_profile.json` (git-ignored)
4. `build_scrape_source()` merges terms into settings once per run

Smoke test limits to **1 term × Remote** on first scrape to avoid rate limits.
Use `scripts/run_scrape.py` for production runs with full search terms and interactive targeting.

Browser profile directories under `data/browser_profiles/` contain login cookies — never commit them.

## Known limitations / next steps

- [x] Local web tracker (`docker compose up web`)
- [x] Application tracking in SQLite + web UI (`date_applied`, status, notes)
- [x] Title + match-score filters for CSV export
- [ ] Proxy rotation for ZipRecruiter (403 without proxies is expected; logged and skipped)
- [x] Five-source sequential pipeline (Indeed, LinkedIn, Glassdoor, Google, ZipRecruiter)
- [x] Dedicated `scripts/run_scrape.py` (skip résumé re-ingest on repeat runs)

## Legal

Scraping may violate site Terms of Service. Use at your own risk; respect rate limits.
AgentZero never auto-submits applications.
