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
docker compose run --rm agentzero python scripts/rank_and_sync.py --yes
```

`docker-compose.yml` sets:

- `AGENTZERO_SCRAPE_CDP_URL=http://host.docker.internal:9222`
- `AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=false`
- `AGENTZERO_CDP_ALLOW_DOCKER_HOST=true`
- `AGENTZERO_SEARCH_INTERACTIVE=false`
- `AGENTZERO_SCRAPE_BROWSER_CHANNEL=` (empty — use bundled Chromium, not host Chrome)
- `AGENTZERO_SCRAPE_BROWSER_HEADLESS=true`

Volumes: `./data`, `./resume` (read-only), `./token.json`, `./client_secret.json`.

**Note:** `token.json` and `client_secret.json` must exist on the host (empty placeholder JSON is fine for scrape-only runs). Create from `google_auth.py` when using Sheets sync.

---

## Troubleshooting

| Issue | Action |
|-------|--------|
| CDP connection refused | Confirm host Chrome is running (`launch_chrome_cdp.ps1`) |
| `UnsafeCDPURLError` for docker host | Set `AGENTZERO_CDP_ALLOW_DOCKER_HOST=true` in `.env` |
| `Chromium distribution 'chrome' is not found` | Compose clears `AGENTZERO_SCRAPE_BROWSER_CHANNEL`; do not force `chrome` in container |
| Playwright "Sync API inside asyncio loop" during full scrape | Known when JobSpy runs before browser boards in one process; use host venv for full scrape or scrape boards only via verify script until fixed |
| Build appears stuck | Check `data/.docker-build-status.json`; Playwright step often takes 5+ minutes (`SLOW` vs `STALL?`) |
| LinkedIn login | Use `scripts/import_browser_cookies.py` or interactive run with profile under `data/browser_profiles/` |
| Missing `.env` on compose | Create `.env` from `.env.example`; compose requires `env_file` |

---

## What runs where

| Component | Location |
|-----------|----------|
| Indeed / Glassdoor | Host Chrome via CDP |
| LinkedIn | Container Playwright + mounted `data/browser_profiles/` |
| Google Jobs / ZipRecruiter | Container HTTP (JobSpy) |
| LLM + Sheets | Container (keys from env, OAuth files mounted) |
| MCP server | Host `.venv` (not in Docker) |

See also [SECURITY.md](SECURITY.md) (secrets, log redaction) and [SCRAPING.md](SCRAPING.md) (boards, CAPTCHA).
