# Getting started

Install AgentZero, configure scraping with **full Google Chrome** (recommended for CAPTCHA),
and run the daily job-search loop.

For architecture, build history, and operator deep-dives, see the [documentation index](../README.md#documentation).

---

## Requirements

- Python 3.11+ (3.12+ recommended)
- **Google Chrome** installed (not just Playwright’s bundled Chromium)
- OpenAI or Anthropic API key
- Optional: [Docker](DOCKER.md) for containerized pipeline + web tracker on port 8080

---

## 1. Install

```powershell
cd AgentZero
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -e ".[dev,scrape,llm,mcp,web]"
playwright install chrome
copy .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=sk-...
AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome
AGENTZERO_SCRAPE_BROWSER_HEADLESS=false
AGENTZERO_REMOTE_ONLY=true
AGENTZERO_LOCATIONS=Remote
```

Put your résumé in `resume/` (`.docx`, `.pdf`, `.txt`, or `.md`).

### Pre-commit hooks (recommended)

Catch ruff, encoding, and **CodeQL** issues before they reach GitHub:

```powershell
pip install -e ".[dev]"
pre-commit install
pre-commit install --hook-type pre-push
```

- **Every commit:** ruff + UTF-8 encoding check (matches CI)
- **Every push:** CodeQL Python security scan (same class of alerts as the GitHub PR check)

Install the [CodeQL CLI](https://github.com/github/codeql-cli-binaries/releases) once and add
`codeql.exe` to PATH (or set `CODEQL_CLI` to its full path). The pre-push hook takes about 1–3
minutes. Emergency only: `AGENTZERO_SKIP_CODEQL=1 git push`.

Manual run:

```powershell
pre-commit run --all-files
pre-commit run codeql --hook-stage pre-push
python tools/codeql_check.py
```

---

## 2. Browser setup (CAPTCHA / login)

Playwright’s bundled **Chromium** is a small automation window and often fails Cloudflare
Turnstile. Use **installed Chrome** instead (`AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome`).

**One-time per job board:**

LinkedIn — Playwright profile:

```powershell
python scripts/login_job_boards.py --site linkedin
```

Indeed + Glassdoor — **real Chrome** over CDP (MFA / Cloudflare). Close other Chrome windows, then start a **dedicated CDP profile** from the repo root:

**Windows (PowerShell):**

```powershell
.\scripts\launch_chrome_cdp.ps1
```

**macOS / Linux:**

```bash
python scripts/launch_chrome_cdp.py
```

**macOS / Linux (shell — works in zsh):**

```bash
chmod +x scripts/launch_chrome_cdp.sh   # once
./scripts/launch_chrome_cdp.sh
```

The launcher starts Chrome on `127.0.0.1:9223` and a small host proxy on port **9222**
(so Docker can use `host.docker.internal:9222`; Chrome only accepts loopback). Set
`--no-docker-expose` on the launch script to skip the proxy.

Log into Indeed and Glassdoor in that Chrome window. Uncomment in `.env`:

```env
AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:9222

Search snapshots are written to `data/search_profile.json` (not `resume/`), so Docker can keep
`resume/` read-only.
AGENTZERO_SCRAPE_CDP_SITES=indeed,glassdoor
```

Then:

```powershell
python scripts/login_job_boards.py --site indeed,glassdoor
python scripts/verify_browser_session.py --site linkedin,glassdoor,indeed
```

The same launch commands appear on the tracker **Scraper → Chrome CDP** page after `docker compose up web` (http://localhost:8080/scraper).

| Site | Browser mode |
|------|----------------|
| LinkedIn | Playwright profile (`data/browser_profiles/linkedin`) — **enabled by default** |
| Indeed, Glassdoor | CDP — real Chrome (`AGENTZERO_SCRAPE_CDP_URL`); opt in via Scraper or `AGENTZERO_SCRAPE_BROWSER_SITES` |

| Exit code | Meaning | What to do |
|-----------|---------|------------|
| 0 | Ready | Scrape |
| 1 | Login required | Run `login_job_boards.py` again |
| 2 | Blocked (CAPTCHA) | Solve in the Chrome window, or import cookies |

---

## 3. Local job tracker (web UI)

Browse and edit jobs in SQLite from the browser — no Google Sheet required.

```powershell
docker compose up web
# Open http://localhost:8080
```

| Action | Effect |
|--------|--------|
| Column headers | Sort asc/desc |
| Row click | Job card — description, match rationale, status, notes |
| Save status / notes | Updates SQLite (on list or job card) |
| Cover letter | Generate from `resume/` + job (GPT-5.5), edit in pane, Save, Download .txt |
| Nope | Soft-reject (`status=rejected`, hidden by default) |

**Tracker columns** (13 in the web table; full schema in CSV/SQLite export):

`source`, `company`, `title`, `location`, `comp_min`, `comp_max`, `glassdoor_rating`,
`match_score`, `status`, `date_applied`, `notes`, `url`, `job_id`.

Optional CSV backup from the host venv:

```powershell
python -c "from pathlib import Path; from agentzero.config import get_settings; from agentzero.storage.db import Database; from agentzero.storage.csv_export import export_csv; s=get_settings(); db=Database(s.db_path); print(export_csv(db, Path('output/jobs.csv'), min_match_score=s.min_match_score))"
```

See **[DOCKER.md](DOCKER.md)** for container pipeline runs and build caching.

---

## 4. Daily pipeline

**Lead session** (recommended — scrape → review → approve):

```powershell
python scripts/run_lead_session.py
python scripts/run_lead_session.py --all-titles
```

**Classic pipeline** (writes `NEW` directly, no lead gate):

```powershell
python scripts/run_scrape.py --limit 10
python scripts/enrich_jobs.py
python scripts/rank_jobs.py
docker compose up web
```

On each scrape you confirm job titles, locations, and comp floor interactively (unless
`--no-search-prompt` for automation).

---

## 5. Verify install

```powershell
python scripts/smoke_test.py --resume-only
pytest -q
python scripts/estimate_cost.py
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Tiny “automation” browser | Set `AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome` in `.env`; run `playwright install chrome` |
| CAPTCHA loop / Ray ID | Use Chrome channel + `login_job_boards.py`; try cookie import for Glassdoor |
| LinkedIn authwall | `login_job_boards.py --site linkedin` then `verify_browser_session --site linkedin` |
| ZipRecruiter 403 | Expected without proxies; other boards still run |
| UTF-16 garbled files on Windows | `python tools/fix_encoding.py` before git commit |
| Empty web UI | Scrape first; ensure `./data/agentzero.db` exists and is mounted in compose |

Full scraping reference: **[SCRAPING.md](SCRAPING.md)**.

Security and secrets: **[SECURITY.md](SECURITY.md)**.

LLM cost and models: **[COST_AND_MODELS.md](COST_AND_MODELS.md)**.
