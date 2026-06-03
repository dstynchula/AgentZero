# Docker (optional)

Run the AgentZero pipeline in a container while **Chrome for Indeed/Glassdoor stays on the host**
(CDP on port 9222). Secrets live in gitignored `.env` and bind-mounted OAuth files — never in the image.

MCP/Cursor continues to use a local `.venv` on the host ([`AGENTS.md`](../AGENTS.md)).

---

## Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Google Chrome on the **host** for CDP boards
- `.env` copied from `.env.example` (API keys, optional sheet ID)
- Host `.venv` optional for `launch_chrome_cdp.py` (PowerShell script invokes `python` on PATH)

---

## 1. Start host Chrome (CDP)

From the repo root on the **host** (not inside the container):

| Platform | Command |
|----------|---------|
| Windows (PowerShell) | `.\scripts\launch_chrome_cdp.ps1` |
| macOS / Linux | `python scripts/launch_chrome_cdp.py` |
| macOS / Linux (shell) | `./scripts/launch_chrome_cdp.sh` |

Log into Indeed/Glassdoor once in that window.

**How Docker reaches CDP:** Chrome listens on `127.0.0.1:9223` only (security). The launcher also
starts a host TCP proxy on `0.0.0.0:9222` that forwards to Chrome and rewrites `Host:
host.docker.internal` → `127.0.0.1` (Chrome rejects the Docker hostname otherwise). Containers use
`http://host.docker.internal:9222`. Relaunching the script stops stale proxy processes on 9222.

Same commands appear on **Scraper → Chrome CDP** at http://localhost:8080/scraper when the web UI
is running; use **Connect** after Chrome is up.

---

## 2. Build the image (with progress + ETA)

Prefer the wrapper over raw `docker compose build` — it prints elapsed time, ETA total, ETA to next step, and writes `data/.docker-build-status.json` (timings only, no secrets):

```powershell
python scripts/docker_build.py
# or: .\scripts\docker_build.ps1
```

Tune stall detection: `AGENTZERO_BUILD_STALL_SEC=180` (default).

### Faster rebuilds (P30)

The Dockerfile installs dependencies **before** copying the full `agentzero/` tree, and uses a
BuildKit pip cache mount. After the first build, edits under `agentzero/` usually skip the
**pip** and **Playwright** steps (only the final **copy** layer rebuilds).

`docker_build.py` sets `DOCKER_BUILDKIT=1` automatically. Raw builds need the same:

```powershell
$env:DOCKER_BUILDKIT = "1"
docker build -t agentzero:local .
```

For day-to-day web UI work without any rebuild, copy the override example and restart compose:

```powershell
Copy-Item docker-compose.override.yml.example docker-compose.override.yml
docker compose up web
```

`docker-compose.override.yml` is gitignored; it bind-mounts `./agentzero` read-only into
`web` and `agentzero` services.

### Monitored build (stay interactive in Cursor)

While the build runs in a background shell, arm a 30s loop (Option A from the migration plan):

```powershell
while ($true) {
  Start-Sleep -Seconds 30
  Write-Output 'AGENT_LOOP_TICK_docker_build {"prompt":"Read data/.docker-build-status.json. Summarize step, elapsed, ETA total, ETA next. If stalled=true or last_output_at older than 3 min, say STALL and suggest action. Keep response under 5 lines. Do not run docker commands."}'
}
```

Use Cursor `notify_on_output` on `^AGENT_LOOP_TICK_docker_build`, or run `/loop 30s` with the same prompt (Option C).

**Do not** run `docker compose config` in shared logs — it expands secrets from `.env`.

---

## 3. Run pipeline stages

```powershell
docker compose run --rm agentzero python scripts/run_scrape.py --no-search-prompt
docker compose run --rm agentzero python scripts/enrich_jobs.py
docker compose run --rm agentzero python scripts/rank_jobs.py
```

`docker-compose.yml` sets:

- `AGENTZERO_SCRAPE_CDP_URL=http://host.docker.internal:9222`
- `AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=false`
- `AGENTZERO_CDP_ALLOW_DOCKER_HOST=true`
- `AGENTZERO_SEARCH_INTERACTIVE=false`
- `AGENTZERO_SCRAPE_BROWSER_CHANNEL=` (empty — use bundled Chromium, not host Chrome)
- `AGENTZERO_SCRAPE_BROWSER_HEADLESS=true`

Volumes: `./data`, `./resume` (read-only).

---

## 4. Web job tracker (port 8080)

Browse and edit jobs in SQLite from the browser. **Rejected** rows are hidden by default
(soft-delete / “Nope”); use **Show rejected** to review roles you passed on.

```powershell
docker compose up web
# Open http://localhost:8080 — Chat (default); Jobs at /jobs
```

**Chat** (`/`) is the default landing page: an LLM assistant with SQLite session history.
It reads jobs and your search profile; mutating tools (scrape, status, cover letter, leads)
require **Confirm** in the UI (`AGENTZERO_CHAT_MODEL`, default `gpt-5.5`, OpenAI only).

The `web` service uses the same host CDP settings as `agentzero`:

- `AGENTZERO_SCRAPE_CDP_URL=http://host.docker.internal:9222`
- `AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=false` (Connect **probes** only; launch Chrome on the host)
- `AGENTZERO_CDP_ALLOW_DOCKER_HOST=true`

Start Chrome on the host first (`launch_chrome_cdp.ps1` / `.py`). The launcher starts Chrome on
`127.0.0.1:9223` and a small TCP proxy on `0.0.0.0:9222` (Chromium only binds loopback; Docker
cannot reach `127.0.0.1` on the host). Then use **Connect** on Scraper.

| Action | Effect |
|--------|--------|
| **Chat** (`/`) | LLM assistant — read tracker/profile; Confirm before mutations |
| **Jobs** (`/jobs`) | Sortable table; filters (company, title, status, score, comp); **Enrich selected** batch; soft-reject filter; job card on row click |
| **Save status** | Updates SQLite (e.g. `lead` → `new`) |
| **Save notes** | Updates `notes` on the row |
| **Nope** | Sets `status=rejected` (row stays in DB for dedupe; hidden by default) |
| **Show rejected** | Lists noped roles |
| **Column headers** | Sort asc/desc (default: `match_score` desc) |
| **Row click** | Opens a **job card** — rationale, description, status, notes, **Enrich**, **cover letter** (generate, edit, download .txt) |
| **Scraper** (`/scraper`) | Enable/disable scrape sources, start a background scrape, CDP setup instructions (`/config` redirects) |

**Cover letters** use `AGENTZERO_COVER_LETTER_MODEL` (default `gpt-5.5`; OpenAI only). Files land in
`output/cover_letters/` on the mounted project tree (gitignored).

**Scraper** saves source toggles to `data/web_operator_config.json` (beside the DB). Background
scrapes use `data/search_profile.json` (beside the DB; résumé files stay in read-only `resume/`)
and need an LLM API key; new rows land as `lead`. **Fast scrape** (default) skips per-row LinkedIn
detail pages — LEAD rows persist immediately; use **Enrich** / **Enrich selected** for detail fetch
(~5 parallel browser workers; `AGENTZERO_ENRICH_BROWSER_MAX_CONCURRENCY`). Re-scrapes skip `job_id`s
already in SQLite. Scrapes run in a **child process** so sync
Playwright is not blocked by Uvicorn's asyncio loop; live progress is written to
`data/scrape_progress.json` and polled by the UI (~500ms). Each poll includes granular fields:
`step_id`, `step_label`, `step_elapsed_ms`, `run_elapsed_ms`, `next_step_id`, `next_step_label`,
`plan` (pipeline checklist), `extra` (query/board metadata), `pid`, and `logs` (activity log:
timestamped info/warn/error lines from pipeline steps and Python logging). Stale runs (worker died but
progress still says `running`) are flagged with `stale: true` on `GET /api/scraper`.

Stop a background scrape: **Stop scrape** on `/scraper`, `POST /scraper/scrape/stop`, or
`POST /api/scraper/stop` (JSON includes updated `scrape` status).

Chrome CDP must run on the **host** — Scraper shows PS1, Python, and shell launch commands plus env vars.
When Chrome returns a loopback WebSocket URL (`127.0.0.1:9223`), the scraper rewrites it to
`host.docker.internal:9222` and attaches with Playwright `connect_over_cdp(rewritten_ws)`.

Use the header **Dark mode** toggle (stored in the browser). JSON: `GET /api/scraper`, `GET /api/enrich`.

Batch enrich progress is written to `data/enrich_progress.json` (same shape as scrape progress).

Long table cells are truncated; hover for the full value, or open the job card.

The `web` service mounts `./data` and `./resume` (read-only). Rebuild the image
after pulling web changes (`python scripts/docker_build.py`) so `uvicorn` and FastAPI are installed.

**Security:** the UI has **no login**. Bind to localhost via your firewall or Docker port mapping;
do not expose port 8080 on untrusted networks. See [SECURITY.md](SECURITY.md).

---

## Troubleshooting

| Issue | Action |
|-------|--------|
| CDP connection refused | Start host Chrome (`launch_chrome_cdp.ps1` / `.py` / `.sh`) |
| Connect says “Chrome not found” in Docker | Web container cannot launch host Chrome; restart `docker compose up web` so CDP URL is `host.docker.internal`, not `127.0.0.1` |
| Connect fails but Chrome is on 9222 (host) | Close Chrome and relaunch via `launch_chrome_cdp` (starts loopback Chrome + `0.0.0.0:9222` proxy for Docker) |
| Connect fails; host `curl :9222` works | Restart `launch_chrome_cdp` so the proxy rewrites `Host: host.docker.internal` → `127.0.0.1` (Chrome rejects the Docker hostname) |
| `UnsafeCDPURLError` for docker host | Set `AGENTZERO_CDP_ALLOW_DOCKER_HOST=true` in `.env` |
| `Chromium distribution 'chrome' is not found` | Compose clears `AGENTZERO_SCRAPE_BROWSER_CHANNEL`; do not force `chrome` in container |
| Playwright "Sync API inside asyncio loop" during full scrape | Fixed in P48: web scrapes run in a subprocess; rebuild the `web` image after pulling P48+ |
| CDP `ECONNREFUSED 127.0.0.1:9223` from Docker web scrape | Fixed in P48: Playwright rewrites Chrome's loopback WebSocket URL to `host.docker.internal:9222`; ensure `AGENTZERO_CDP_ALLOW_DOCKER_HOST=true` and relaunch host Chrome via `launch_chrome_cdp` |
| Full scrape still fails after P48 | Confirm host proxy on `0.0.0.0:9222`, **Connect** succeeds on Scraper, and `docker compose up web --build` picked up the new image |
| Build appears stuck | Check `data/.docker-build-status.json`; Playwright step often takes 5+ minutes (`SLOW` vs `STALL?`) |
| Every code change re-runs pip/Playwright | Ensure BuildKit is on; pull P30+ Dockerfile; use override bind-mount for hot reload |
| LinkedIn login | Use `scripts/import_browser_cookies.py` or interactive run with profile under `data/browser_profiles/` |
| Missing `.env` on compose | Create `.env` from `.env.example`; compose requires `env_file` |

---

## What runs where

| Component | Location |
|-----------|----------|
| Indeed / Glassdoor | Host Chrome via CDP (recommended) |
| LinkedIn | Container Playwright + mounted `data/browser_profiles/` (or host CDP when configured) |
| All three boards | Production stack is browser-only — see [SCRAPING.md](SCRAPING.md) |
| LLM rank | Container (keys from env) |
| MCP server | Host `.venv` (not in Docker) |
| Web job tracker | Container `web` service → http://localhost:8080 |

See also [SECURITY.md](SECURITY.md) (secrets, log redaction) and [SCRAPING.md](SCRAPING.md) (boards, CAPTCHA).
