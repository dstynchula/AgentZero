# Getting started

Install AgentZero, configure scraping with **full Google Chrome** (recommended for CAPTCHA),
and run the daily job-search loop.

For architecture, build history, and operator deep-dives, see the [documentation index](../README.md#documentation).

---

## Requirements

- Python 3.11+ (3.12+ recommended)
- **Google Chrome** installed (not just Playwright’s bundled Chromium)
- OpenAI or Anthropic API key
- Optional: Google Cloud OAuth client for Sheets sync

---

## 1. Install

```powershell
cd AgentZero
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -e ".[dev,scrape,llm,google,mcp]"
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

---

## 2. Browser setup (CAPTCHA / login)

Playwright’s bundled **Chromium** is a small automation window and often fails Cloudflare
Turnstile. Use **installed Chrome** instead (`AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome`).

**One-time per job board:**

```powershell
# LinkedIn — Playwright profile (works well as-is)
python scripts/login_job_boards.py --site linkedin

# Indeed + Glassdoor — your real Chrome (MFA / Cloudflare)
# Close Chrome, then:
.\scripts\launch_chrome_cdp.ps1
# Uncomment AGENTZERO_SCRAPE_CDP_URL in .env, then:
python scripts/login_job_boards.py --site indeed,glassdoor

python scripts/verify_browser_session.py --site linkedin,glassdoor,indeed
```

| Site | Browser mode |
|------|----------------|
| LinkedIn | Playwright profile (`data/browser_profiles/linkedin`) |
| Indeed, Glassdoor | CDP — real Chrome (`AGENTZERO_SCRAPE_CDP_URL`) |

**Playwright + system Chrome:** AgentZero no longer passes `--disable-blink-features=AutomationControlled`
or `--enable-automation` when `AGENTZERO_SCRAPE_BROWSER_CHANNEL=chrome` (those cause yellow flag banners).

| Exit code | Meaning | What to do |
|-----------|---------|------------|
| 0 | Ready | Scrape |
| 1 | Login required | Run `login_job_boards.py` again |
| 2 | Blocked (CAPTCHA) | Solve in the Chrome window, or import cookies (below) |

**If Glassdoor stays blocked:** log in with your daily Chrome, export cookies with the
[Cookie-Editor](https://cookie-editor.cgagnier.ca/) extension, then:

```powershell
python scripts/import_browser_cookies.py --site glassdoor --from cookies.json
```

Optional: warm up a single board without the full scrape:

```powershell
python scripts/open_glassdoor_browser.py
python scripts/open_indeed_browser.py
```

---

## 3. Google Sheets (optional)

```powershell
# Download Desktop OAuth client → client_secret.json
python scripts/google_auth.py
# Set AGENTZERO_SHEET_ID in .env
python scripts/sync_sheets.py --dry-run
```

**Tracker columns** (Google Sheet — 13 columns; full data stays in SQLite/CSV):

`source`, `company`, `title`, `location`, `comp_min`, `comp_max`, `glassdoor_rating`,
`match_score`, `status`, `date_applied`, `notes`, `url`, `job_id` (hide `job_id` in Sheets).

Edit **`date_applied`**, **`status`**, and **`notes`** — every sync imports them into SQLite first.

Only jobs with **match_score ≥ 0.75** export by default (`AGENTZERO_MIN_MATCH_SCORE`).
Applied jobs (with `date_applied` set) always appear regardless of score. Unranked jobs
export until you run rank.

Restore applied companies from the sheet after a DB purge:

```powershell
python scripts/import_sheet_status.py --dry-run
python scripts/import_sheet_status.py --sync
```

---

## 4. Daily pipeline

**Lead session** (recommended — scrape → review → approve → sheet):

```powershell
python scripts/run_lead_session.py
python scripts/run_lead_session.py --all-titles
```

**Classic pipeline** (writes `NEW` directly, no lead gate):

```powershell
python scripts/run_scrape.py --limit 10
python scripts/enrich_jobs.py
python scripts/rank_and_sync.py --yes
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

Full scraping reference: **[SCRAPING.md](SCRAPING.md)**.

Security and secrets: **[SECURITY.md](SECURITY.md)**.

LLM cost and models: **[COST_AND_MODELS.md](COST_AND_MODELS.md)**.
