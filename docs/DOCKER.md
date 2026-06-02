# Docker (optional)

Run the AgentZero pipeline in a container while **Chrome for Indeed/Glassdoor stays on the host**
(CDP on port 9222). Secrets live in gitignored `.env` and bind-mounted OAuth files — never in the image.

MCP/Cursor continues to use a local `.venv` on the host ([`AGENTS.md`](../AGENTS.md)).

---

## Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Google Chrome on the **host** for CDP boards
- `.env` copied from `.env.example` (API keys, optional sheet ID)
- Optional: `token.json` and `client_secret.json` for Sheets sync

---

## 1. Start host Chrome (CDP)

```powershell
.\scripts\launch_chrome_cdp.ps1
```

Log into Indeed/Glassdoor once in that window. The container reaches it via `host.docker.internal:9222`.

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
# Open http://localhost:8080
```

| Action | Effect |
|--------|--------|
| **Save status** | Updates SQLite (e.g. `lead` → `new`) |
| **Save notes** | Updates `notes` on the row |
| **Nope** | Sets `status=rejected` (row stays in DB for dedupe; hidden by default) |
| **Show rejected** | Lists noped roles |
| **Column headers** | Sort asc/desc (default: `match_score` desc) |
| **Row click** | Opens a **job card** with full details (rationale, description, links) |

Long table cells are truncated; hover for the full value, or open the job card.

The `web` service mounts `./data` only. Rebuild the image
after pulling web changes (`python scripts/docker_build.py`) so `uvicorn` and FastAPI are installed.

**Security:** the UI has **no login**. Bind to localhost via your firewall or Docker port mapping;
do not expose port 8080 on untrusted networks. See [SECURITY.md](SECURITY.md).

---

## Troubleshooting

| Issue | Action |
|-------|--------|
| CDP connection refused | Confirm host Chrome is running (`launch_chrome_cdp.ps1`) |
| `UnsafeCDPURLError` for docker host | Set `AGENTZERO_CDP_ALLOW_DOCKER_HOST=true` in `.env` |
| `Chromium distribution 'chrome' is not found` | Compose clears `AGENTZERO_SCRAPE_BROWSER_CHANNEL`; do not force `chrome` in container |
| Playwright "Sync API inside asyncio loop" during full scrape | Known when JobSpy runs before browser boards in one process; use host venv for full scrape or scrape boards only via verify script until fixed |
| Build appears stuck | Check `data/.docker-build-status.json`; Playwright step often takes 5+ minutes (`SLOW` vs `STALL?`) |
| Every code change re-runs pip/Playwright | Ensure BuildKit is on; pull P30+ Dockerfile; use override bind-mount for hot reload |
| LinkedIn login | Use `scripts/import_browser_cookies.py` or interactive run with profile under `data/browser_profiles/` |
| Missing `.env` on compose | Create `.env` from `.env.example`; compose requires `env_file` |

---

## What runs where

| Component | Location |
|-----------|----------|
| Indeed / Glassdoor | Host Chrome via CDP |
| LinkedIn | Container Playwright + mounted `data/browser_profiles/` |
| Google Jobs / ZipRecruiter | Container HTTP (JobSpy) |
| LLM rank | Container (keys from env) |
| MCP server | Host `.venv` (not in Docker) |
| Web job tracker | Container `web` service → http://localhost:8080 |

See also [SECURITY.md](SECURITY.md) (secrets, log redaction) and [SCRAPING.md](SCRAPING.md) (boards, CAPTCHA).
