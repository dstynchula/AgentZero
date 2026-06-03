# P48 — Docker web scrape fix

**Branch:** `feat/docker-web-scrape-fix` · **Epic:** docker-scrape

## Mission

Full three-board scrapes from the Docker web UI (Scraper or chat HITL `start_scrape`) without
`ECONNREFUSED 127.0.0.1:9223` on CDP boards or Playwright **Sync API inside the asyncio loop**.

## Changes

| Task | Summary |
|------|---------|
| T01 | `resolve_cdp_ws_endpoint()` rewrites loopback WS → `host.docker.internal:9222`; `connect(ws_endpoint=…)` in Docker |
| T02 | `ScrapeRunner` spawns `multiprocessing.Process` worker; parent polls `data/scrape_progress.json` |
| T03 | `docs/DOCKER.md` troubleshooting + this ledger in `PROGRESS.md` |

## Manual smoke

1. Host: `.\scripts\launch_chrome_cdp.ps1`
2. `docker compose up web --build`
3. Scraper → **Connect** → **Start background scrape**
4. Indeed/Glassdoor attach via `host.docker.internal:9222`; LinkedIn uses container Chromium; progress bar advances.

## Epic Accept

```bash
pytest tests/test_cdp_ws_endpoint.py tests/scrape/test_launch_browser.py tests/test_scrape_runner_progress.py tests/test_web_chat_hitl.py -q
ruff check agentzero/scrape/browser_common.py agentzero/web/scrape_runner.py tests/test_cdp_ws_endpoint.py tests/scrape/test_launch_browser.py tests/test_scrape_runner_progress.py
python tools/encoding_check.py
```
