# AgentZero

[![CI](https://github.com/dstynchula/AgentZero/actions/workflows/ci.yml/badge.svg)](https://github.com/dstynchula/AgentZero/actions/workflows/ci.yml)

AgentZero is a **local, résumé-driven job search agent**. Drop your résumé in `resume/`, run a
daily pipeline, and it will:

- Scrape **five job boards** (Indeed, LinkedIn, Glassdoor, Google Jobs, ZipRecruiter)
- **Enrich** listings (comp, company size, Glassdoor, careers URLs)
- **Rank** jobs against your résumé with an LLM
- Mirror everything to **SQLite** and a **local web tracker** (Docker on port 8080)
- Track applications you mark in the UI — it never auto-submits

Built as a working tool, AgentZero further serves as a working demonstration of agentic
development techniques that produce reliable, well-tested code, alongside a secure and
operator-controlled workflow for ingesting, validating, enriching, and distilling complex
external data into actionable intelligence — an open-book example of agentic co-programming in
Cursor (Ralph loop, TDD gates, human-in-the-loop where it matters).

---

## Architecture at a glance

Vertical pipeline (data flows top → bottom). Operator tools and build stack on the right.

```mermaid
flowchart TB
    subgraph IN["Ingest"]
        R["resume/ · python-docx · pypdf"]
        P["Search profile · LLM + Pydantic models"]
    end

    subgraph SC["① Scrape — Playwright · JobSpy · httpx"]
        CDP["Host Chrome · CDP :9222"]
        BR["Indeed · LinkedIn · Glassdoor"]
        JS["Google Jobs · ZipRecruiter"]
    end

    V["② Validate — schema gate · quarantine table"]
    E["③ Enrich — detail fetch · Glassdoor · DuckDuckGo"]
    RK["④ Rank — OpenAI / Anthropic · pydantic-settings"]
    DB[("⑤ SQLite — data/agentzero.db · stable job_id")]
    LD["⑥ Lead — status=lead in DB"]
    OP["⑦ Review — Cursor MCP · run_lead_session.py"]
    AP["⑧ Promote — LEAD → NEW"]
    UI["⑨ Tracker — Docker · FastAPI · Jinja2 · :8080"]

    R --> P --> SC
    CDP --> BR
    BR --> V
    JS --> V
    V --> E --> RK --> DB --> LD --> OP --> AP --> UI

    subgraph BUILD["Built with — agentic loop"]
        direction TB
        CUR["Cursor · Ralph · TDD · prep-pr"]
        PYT["Python 3.12 · pytest · ruff"]
        GHA["GitHub Actions · CodeQL · docker-build"]
        PDY["Pydantic v2 · FastMCP stdio"]
    end

    OP -.-> CUR
    RK -.-> OAI["OpenAI gpt-5-nano default"]
    UI -.-> PDY
```

| Layer | Tools |
|-------|--------|
| Config | **Pydantic Settings**, `.env`, typed `Settings` |
| Scrape | **Playwright**, host **Chrome CDP**, **JobSpy**, BeautifulSoup |
| Intelligence | **OpenAI** / Anthropic APIs, résumé-driven rank prompts |
| Storage | **SQLite**, idempotent upsert, pipeline status columns |
| Operator | **Cursor** + **FastMCP** lead session, **Docker** web service |
| Quality | **pytest**, **ruff**, CI, Ralph `PROGRESS.md` / `WORKLOG.md` |

---

## Design tradeoffs

- **Local-first trust boundary**: data and credentials stay on your machine; MCP is stdio-only
- **Lead-gated workflow**: new jobs land as `lead` in SQLite first; approve to promote to the web tracker
- **Local tracker**: browse, edit status/notes, and soft-reject in the web UI — no external spreadsheet
- **Scrape reliability over elegance**: browser/CDP paths are explicit and operationally opinionated
- **Security pragmatism**: SSRF defenses are strongest on enrichment HTTP; board scraping intentionally navigates board URLs

---

## Quality bar

- **CI enforced**: `ruff`, full `pytest -q`, UTF-8/UTF-16 encoding guard (`.github/workflows/ci.yml`)
- **TDD + regression coverage** on parser drift, lead/export policy, and session safety paths
- **Idempotent pipeline design** via stable `job_id` and per-stage status gates
- **Explicit operator safety**: no auto-apply, no silent scrape/commit in MCP interactive flow

---

## Quick start

**New users:** follow **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)** (install, Chrome
for CAPTCHA, daily loop).

```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -e ".[dev,scrape,llm,mcp]"
playwright install chrome
copy .env.example .env                # set OPENAI_API_KEY + SCRAPE_BROWSER_CHANNEL=chrome
docker compose up web                 # optional: job tracker at http://localhost:8080
python scripts/login_job_boards.py --site linkedin,glassdoor
python scripts/smoke_test.py
pytest -q
```

Dependencies are grouped in `pyproject.toml`: `dev`, `scrape`, `llm`, `mcp`, `web`.

**Docker (optional):** run the pipeline in a container with host Chrome via CDP — see
**[docs/DOCKER.md](docs/DOCKER.md)**. Build with `python scripts/docker_build.py` for elapsed/ETA progress.
Use `docker compose up web` for a local job tracker on port 8080 (edit status/notes, soft-reject).

**Docker + Indeed/Glassdoor:** on the host run `.\scripts\launch_chrome_cdp.ps1` (Chrome on
`127.0.0.1:9223` plus a proxy on **9222** for `host.docker.internal`). Open Scraper → **Connect**
after `docker compose up web`.

---

## How to use it

### 1. Prepare

1. Put your résumé in `resume/` (gitignored).
2. Copy `.env.example` → `.env` and set `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`).
3. Set **`AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome`** — use full Chrome, not bundled Chromium, for CAPTCHA.
4. For Indeed/Glassdoor CDP: `.\scripts\launch_chrome_cdp.ps1` on the host (see [Getting started](docs/GETTING_STARTED.md)).
5. Run `docker compose up web` (or use host `.venv` + MCP) to review jobs at http://localhost:8080; in Docker, use Scraper → **Connect** to verify CDP.
6. On Windows, dot-source `scripts/dev-env.ps1` to avoid UTF-16 file corruption.

### 2. Daily pipeline

**Recommended — interactive lead session** (scrape → review → approve → web tracker):

```powershell
python scripts/run_lead_session.py              # prompts for titles/locations/comp
python scripts/run_lead_session.py --all-titles # query every title, not just the first
```

Or the classic non-gated pipeline:

```powershell
python scripts/run_scrape.py          # scrape → validate → shallow enrich → SQLite
python scripts/enrich_jobs.py         # deep enrich: detail pages, Glassdoor, web search
python scripts/rank_jobs.py                 # LLM rank vs résumé
docker compose up web                       # browse / edit tracker
```

| Stage | What it does |
|-------|----------------|
| **Scrape** | Five boards, sequential; prompts for titles, locations, comp floor |
| **Lead review** | New roles land as `lead` in SQLite; approve before they appear in the web tracker |
| **Shallow enrich** | Parse comp/size/Glassdoor from fields on the job; filter by comp floor |
| **Deep enrich** | Fetch posting URLs, Glassdoor lookup, DuckDuckGo company research |
| **Rank** | LLM fit score + rationale vs your résumé |
| **Tracker** | Web UI on :8080 — edit status, notes, cover letters, soft-reject; CSV export optional |

### Web tracker and Scraper

| URL | Purpose |
|-----|---------|
| http://localhost:8080/ | Sortable job table; job card — status, notes, **cover letter** (generate, edit, download .txt) |
| http://localhost:8080/scraper | **Scraper** — scrape sources, load résumé, add/remove search titles, background scrape, Chrome CDP **Connect** (`/config` redirects here) |

Scraper persists operator choices in `data/web_operator_config.json`; LLM search snapshots go to
`data/search_profile.json` (see [Docker](docs/DOCKER.md) for host CDP + read-only `resume/` mount).

**Cover letters** on the job card use `AGENTZERO_COVER_LETTER_MODEL` (default `gpt-5.5`, OpenAI only).
Drafts are saved under `output/cover_letters/` (gitignored); edit in the browser and download as `.txt`.

**Backfill** (repair existing DB rows without a full re-scrape):

```powershell
python scripts/backfill_linkedin_comp.py
python scripts/backfill_glassdoor_companies.py
```

### 3. Search targeting

On every scrape, AgentZero reads your latest résumé, uses the LLM to infer search terms and
locations, then **prompts you** to confirm:

- Job titles (most recent role first)
- **Remote-only** by default (`AGENTZERO_REMOTE_ONLY=true`) — United States remote filter; on-site/hybrid listings are dropped (applied jobs are protected)
- Work mode (remote USA vs in-office cities) only when `REMOTE_ONLY=false`
- **Minimum acceptable salary** — listings are kept when the **top of the posted range** meets or
  exceeds this floor (e.g. $230k)

### 4. Quality filters

AgentZero layers filters so the tracker stays actionable:

| Stage | What | Config |
|-------|------|--------|
| **Scrape** | Title must match search terms; hard-reject marketing/HR/etc. | `AGENTZERO_SEARCH_TERMS` |
| **Remote** | Drop on-site/hybrid unless you've applied | `AGENTZERO_REMOTE_ONLY=true` |
| **Rank** | LLM scores each job 0.0–1.0 vs your résumé | `rank_jobs.py` |
| **Export** | CSV omits jobs below match floor; applied jobs always export | `AGENTZERO_MIN_MATCH_SCORE=0.75` (set `0` to disable) |

Jobs below the export floor **remain in SQLite** — lower the floor or open the web UI to review them.

### 6. Application tracking

Use the **web UI** (`docker compose up web` → http://localhost:8080) or edit SQLite via scripts:

- `status` — `lead`, `new`, `applied`, `rejected`, `offer`, etc.
- `date_applied` — marks a role as applied; protects from purges
- `notes`

The web table shows 13 columns; `export_csv` writes the full 24-column schema from SQLite.

### 7. MCP agent (Cursor)

Enable the project MCP server (`.cursor/mcp.json` is included) or register manually.
Requires `pip install -e ".[mcp]"` so `fastmcp` is in `.venv`.

**Windows** (`.cursor/mcp.json` default):

```json
{
  "command": "${workspaceFolder}/.venv/Scripts/python.exe",
  "args": ["-m", "agentzero.mcp_server", "--stdio"],
  "cwd": "${workspaceFolder}"
}
```

**macOS/Linux:** change `Scripts/python.exe` → `bin/python`.

The MCP server includes **interactive workflow instructions** — the agent should run the
lead session **in chat**, confirming with you before each scrape and lead commit:

1. `lead_session_workflow` / `suggest_targets` — propose titles/locations/comp
2. `check_sessions` — verify logins (CDP Chrome **auto-starts** when not running)
3. `run_scrape` — after you confirm parameters
4. Present scored roles; `commit_leads` only for job_ids you select

Same core as `scripts/run_lead_session.py`. See also `AGENTS.md`.

### 8. Scraping notes

Snapshot saved to `data/search_profile.json` (gitignored; beside the DB). Skip the prompt only for CI:
`run_scrape.py --no-search-prompt`.

Defaults: **Indeed, LinkedIn, Glassdoor** via Playwright + **Chrome**; **Google Jobs, ZipRecruiter** via JobSpy HTTP.

```powershell
python scripts/verify_browser_session.py --site linkedin   # before first scrape
python scripts/run_scrape.py --limit 5
```

- Visible **Chrome** window (`AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome`) — complete CAPTCHA once per board.
- ZipRecruiter may 403 without proxies (`AGENTZERO_PROXIES=host:port`).

Full operator guide: **[docs/SCRAPING.md](docs/SCRAPING.md)**.

---

## Documentation

### Use AgentZero (install and daily loop)

| Doc | Contents |
|-----|----------|
| **[Getting started](docs/GETTING_STARTED.md)** | Install, Chrome/CAPTCHA setup, daily pipeline, troubleshooting |
| **[Docker](docs/DOCKER.md)** | Container runs; host Chrome CDP + proxy for `host.docker.internal`; web Scraper **Connect** |
| [Web UI UX spike plan](docs/web-ui-ux-spike.plan.md) | P34 — compact centered table, CDP-off defaults, hide CDP card |
| [Scraping](docs/SCRAPING.md) | Boards, scripts, rate limits, browser sessions, filters |
| [Security](docs/SECURITY.md) | Secrets, SSRF, LLM data, web UI exposure |
| [Cost & models](docs/COST_AND_MODELS.md) | LLM pricing, model selection, knobs |

### Build and architecture (contributors / curious readers)

| Doc | Contents |
|-----|----------|
| [How AgentZero Was Built](docs/BUILD_STORY.md) | Cursor / Ralph loop / TDD story |
| [Original build plan](docs/agentzero_job_hunter_d85b7004.plan.md) | Architecture, 22-task DAG |
| [examples/job_sources.json](docs/examples/job_sources.json) | Reference list of core sources (not loaded at runtime) |
| [PROGRESS.md](PROGRESS.md) | MVP + post-MVP checkbox ledger |
| [WORKLOG.md](WORKLOG.md) | Append-only build history |
| [Public release checklist](docs/PUBLIC_RELEASE_CHECKLIST.md) | What to include/exclude before publishing |

---

## Cost

### Runtime (scrape + rank)

**Pricing estimates as of 2026-05-29.** A full scrape-and-rank run usually costs **~$0.01–0.10**
depending on model and how many unique jobs are ranked.

| Model (OpenAI) | ~100 jobs ranked |
|----------------|------------------|
| **gpt-5-nano** (default) | **~$0.02** |
| gpt-4o-mini | ~$0.06 |

```powershell
python scripts/estimate_cost.py   # estimate from your .env
```

See **[Cost and model selection](docs/COST_AND_MODELS.md)** for criteria, truncation knobs, and
monthly ballparks.

### Building AgentZero (Cursor)

This repo was built in a few focused days with **Cursor** (Ralph loop, TDD, MCP lead session) —
not a months-long contractor engagement.

| Item | Ballpark |
|------|----------|
| Cursor Pro | **~$20/month** |
| Effective daily | **~$20 ÷ 30 ≈ $0.67/day** |
| ~4 build days | **($20 ÷ 30) × 4 ≈ $2.70** in subscription time |

That is the IDE/co-pilot line item only — add negligible **OpenAI** usage during development
(smoke tests, rank tuning) on top. The payoff is a maintained, tested pipeline you run locally
for pennies per scrape instead of paying for a hosted job-search SaaS.

---

## Disclaimer

Scraping job boards may violate site Terms of Service. Use at your own risk; respect rate limits.
AgentZero queues applications for human review and does not auto-submit.

**Privacy:** Résumé and job text are sent to your configured LLM provider when ingest/rank
features run. See **[docs/SECURITY.md](docs/SECURITY.md)** for secrets and network egress.

**Windows:** If markdown or TOML won't render, run `python tools/fix_encoding.py` before committing.
