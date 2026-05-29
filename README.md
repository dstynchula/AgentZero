# AgentZero

Resume-driven, open-source job-hunting agent: multi-board sourcing, enrichment, ranking,
voice-matched cover letters, and a human-in-the-loop application tracker.

## How this repo was built (open book)

This project is both a **working tool** and a **reference model for agentic co-programming**.
It was built in Cursor using a structured Ralph loop: Plan mode architecture, 22 TDD-gated
tasks, parallel waves, and test-driven acceptance criteria — human in the loop where it matters.

- **[How AgentZero Was Built](docs/BUILD_STORY.md)** — narrative for reviewers and recruiters
- **[Original build plan (archived)](docs/agentzero_job_hunter_d85b7004.plan.md)** — full spec, DAG, task ledger
- **[PROGRESS.md](PROGRESS.md)** — task completion ledger
- **[WORKLOG.md](WORKLOG.md)** — append-only build audit trail

## Windows development (UTF-8)

PowerShell can default to UTF-16 for `Out-File` / `Set-Content`, which breaks Python, TOML,
and git diffs. Before editing files in this repo, set UTF-8 for the session:

```powershell
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
```

Or dot-source the project helper from the repo root:

```powershell
. .\scripts\dev-env.ps1
```

If any file still ends up UTF-16, normalize before staging:

```powershell
python tools/fix_encoding.py
```

## Resume-linked search terms

Drop your résumé in `resume/` (gitignored except `.gitkeep`). On **every scrape run**, AgentZero:

1. Reads the latest résumé in `resume/`
2. Uses the LLM to extract `search_terms`, `recent_roles` (newest job first), locations, salary floor
3. Builds search terms with **most recent job titles first**, then related keywords
4. Saves a local snapshot to `resume/search_profile.json` (git-ignored, inspection only)

Pass an LLM to `JobSpySource(..., llm=provider)` or run `ingest_resume()` to populate search terms without an LLM, `.env` search terms are used as-is.

Example snapshot fields: `search_terms`, `recent_roles`, `locations`, `salary_min`.

## Quick start

```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

Build progress is tracked in `PROGRESS.md` (checkboxes) and `WORKLOG.md` (append-only history).

## Disclaimer

Scraping job boards may violate site Terms of Service. Use at your own risk; respect rate limits.
AgentZero queues applications for human review and does not auto-submit.
