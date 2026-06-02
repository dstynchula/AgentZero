# AgentZero build progress

Mutable checkbox ledger for the Ralph build loop and post-MVP runtime work.
The loop re-reads this file each iteration. WORKLOG.md is append-only history.

## MVP build (T01-T22) - complete

- [x] T01 Scaffold (pyproject, pytest, PROGRESS, WORKLOG, .gitignore)
- [x] T02 Config (pydantic-settings)
- [x] T03 Core models (JobPosting, stable_job_id) - 100% cov
- [x] T04 Storage SQLite (idempotent upsert, quarantine) - 100% cov
- [x] T05 Resume ingest
- [x] T06 Voice ingest
- [x] T07 Source interface + RawRecord
- [x] T08 JobSpy source
- [x] T09 Validation gate (deterministic) - 100% cov
- [x] T10 Validation self-correct (LLM) + health - 100% cov
- [x] T11 Playwright/ATS + Glassdoor source
- [x] T12 Enrichment (comp 100% cov)
- [x] T13 LLM provider (OpenAI/Anthropic)
- [x] T14 Ranking/matcher
- [x] T15 Cover letters
- [x] T16 CSV export
- [x] T17 Sheets sync
- [x] T18 Google auth + Gmail/Calendar/Drive
- [x] T19 HITL apply queue
- [x] T20 Runtime Ralph loop + LangGraph pipeline
- [x] T21 FastMCP server
- [x] T22 Publish polish (README, LICENSE, fixtures)

## Post-MVP - documentation and runtime hardening

- [x] P01 Build story + archived plan in docs/; linked from README
- [x] P02 LLM cost docs, estimate_cost.py, rank truncation, search cache, gpt-5-nano default
- [x] P03 Google OAuth script; Sheet ID URL normalization
- [x] P04 Playwright Indeed + sequential JobSpy; docs/SCRAPING.md; SQLite thread lock
- [x] P05 python-docx/pypdf core deps; smoke_test.py
- [x] P06 First live scrape to SQLite (10 Indeed jobs; visible browser for CAPTCHA)
- [x] P07 Sheets sync CLI from populated DB (scripts/sync_sheets.py)
- [x] P08 Interactive search targeting before each scrape run
- [x] P09 Dedicated run_scrape.py CLI; full test suite green (125 tests)
- [x] P10 Work mode prompt (remote USA vs in-office) + LinkedIn/Glassdoor browser scrapers
- [x] P11 Five-source scrape pipeline (primary query, CAPTCHA cap, factory cleanup)
- [x] P12 Deep enrichment (detail fetch, Glassdoor, DuckDuckGo, batch runner, careers URLs)
- [x] P13 Pre-public hardening (SSRF redirects, comp floor, token scrub, sync/prune --yes, CI)
- [x] P14 README restructure; docs/SECURITY.md; 206 tests + ruff in CI
- [x] P15 Rank prompt optimization; reload_settings; script exit codes; PII trim in smoke/auth

## P17 — Reliable browser sessions (TDD Ralph)

- [x] P17a Login vs CAPTCHA page detection + fixtures
- [x] P17b Session health classifier
- [x] P17c verify_browser_session.py CLI
- [x] P17d wait_for_login uses page_needs_login
- [x] P17e open_glassdoor_browser.py
- [x] P17f Optional scrape session preflight
- [x] P17g Docs + .env Chrome channel default
- [x] P17h Live acceptance — verify linkedin exit 1 (authwall); glassdoor exit 2 (blocked); operator login next

## P16 — YAGNI prune + sheet slimming (2026-05-30)

- [x] Removed cover-letter generation, voice ingest, HITL apply queue, and unused Gmail/Calendar/Drive wrappers
- [x] Pipeline is scrape → enrich → rank → sheet sync; application state lives in sheet + `tracking.py`
- [x] Slim Google Sheet export (`SHEET_COLUMNS`, 13 cols; full schema in CSV/SQLite)
- [x] Title relevance filter (`title_filter.py`); match-score export gate (`export_filter.py`, `AGENTZERO_MIN_MATCH_SCORE`)

## P18 — Lead-gathering session + tracker hardening (2026-05-31)

- [x] `ApplicationStatus.LEAD` — scrape lands in DB first; sheet sync only after operator approval
- [x] Shared core `agentzero/leads/session.py` (suggest → scrape → review → approve → commit)
- [x] MCP tools: `suggest_targets`, `check_sessions`, `run_scrape`, `list_leads`, `approve_leads`, `commit_leads`
- [x] CLI wizard `scripts/run_lead_session.py` (same core; `--all-titles`, `--yes`)
- [x] `Pipeline.run(new_status=…)` preserves applied/tracker fields on re-scrape
- [x] Sheet `date_applied` auto-promotes pre-application statuses (`lead`, `new`, `reviewed`, …) to `applied`
- [x] Tracker import O(N) index + `dry_run` preview; dedicated CDP Chrome profile (`launch_chrome_cdp.ps1`)
- [x] Docs: README + SCRAPING.md lead session; 271 tests + ruff clean

## P19 — Parser hardening + enrichment fixes (2026-05-31)

- [x] LinkedIn SPA search parser: scoped embedded `jobPosting:{id}` JSON, subtitle/logo company, `formattedSalary` comp
- [x] Pipeline fetches LinkedIn detail pages when comp missing after scrape (`_enrich_scraped_job`)
- [x] Glassdoor employer resolution from partner URLs, slugs, embedded JSON, description patterns (`scrape/glassdoor_company.py`)
- [x] Backfill scripts: `run_linkedin_lead_scrape.py`, `backfill_linkedin_comp.py`, `backfill_glassdoor_companies.py`
- [x] Glassdoor ratings via DuckDuckGo web search when direct Glassdoor HTTP is blocked; skip lookup for `Unknown` company
- [x] Docs + plan updated; temp debug artifacts removed; 285 tests + ruff clean

## P20 — MCP interactive workflow + CDP auto-launch + security hardening (2026-05-31)

- [x] MCP server instructions + `lead_session_workflow` tool; `.cursor/mcp.json`, `AGENTS.md`, Cursor rule
- [x] CDP Chrome auto-launch when endpoint down (`ensure_cdp_ready` / `AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH`)
- [x] CDP URL localhost-only validation; HTTP response size cap (2 MB); OAuth token `chmod 0o600`
- [x] MCP input bounds; `commit_leads` returns actual approved count; CI `persist-credentials: false`
- [x] Docs: SECURITY.md, README, SCRAPING.md; 293 tests + ruff clean

## P21 — Pre-review cleanup (security docs + scrape path consolidation) (2026-05-31)

- [x] P21a Refresh `docs/SECURITY.md` — current pipeline, SSRF scope, LLM untrusted input, token ACLs
- [x] P21b Browser post-navigation SSRF guard in `session_probe.py`
- [x] P21c Remove dead `BrowserIndeedSource`; factory raises when no sources configured
- [x] P21d Windows OAuth token ACL on save (`persist_credentials`)
- [x] P21e Mark `list_pages` / `parse_list` as example-only reference code
- [x] P21f Plan doc post-build ledger + tests green

## P22 — Export filter + doc alignment (2026-06-01)

- [x] Exclude `REJECTED` leads from sheet export (fix `is_application_locked` bleed-through)
- [x] `filter_jobs_for_export` always applies status gates (even when min_score disabled)
- [x] MCP `commit_leads` returns full sheet-rewrite note
- [x] BUILD_STORY, `.env.example`, smoke_test aligned with P16 pipeline
- [x] Tests green (307 tests)

## P23 — Polish nits (2026-06-01)

- [x] Markdown table escaping in `format_lead_preview`
- [x] Clarify `is_application_locked` vs sheet export policy; MCP workflow + SECURITY lead-status notes
- [x] Consolidate MCP imports; fix `llm/provider.py` formatting
- [x] Tests: pipe escape + rejected prune/export split

## P24 — Public launch polish (2026-05-31)

- [x] README: architecture-at-a-glance diagram + design tradeoffs + quality bar
- [x] Added `docs/PUBLIC_RELEASE_CHECKLIST.md` (security, quality, include/exclude guidance)
- [x] README documentation index links the public release checklist
- [x] Ledgers updated; checks re-run (`pytest -q`, `ruff check agentzero tests scripts tools`)

## P25 — Append-only test UTF-8 robustness (2026-05-31)

- [x] `tests/test_worklog_append_only.py` decodes `git show` output as UTF-8 bytes
- [x] Prevent false failures on Windows locale decoding differences
- [x] Full checks green (309 tests + ruff)

## P26 — Meaningful coverage wave (tiered, package-per-PR)

- [x] P26-0 CI coverage report (optional)
- [x] P26a net (≥90%)
- [x] P26b mcp core (≥85%)
- [x] P26c leads (≥75%)
- [x] P26d apply + export_filter (≥90%)
- [x] P26e enrich I/O (≥75%) — PR #17
- [x] P26f pipeline (≥75%) — PR #18
- [x] P26g google import/sync (≥75%) — PR #19
- [x] P26h scrape factory + session (≥70%) — PR #20
- [ ] P26i glassdoor scrape (≥70%)
- [ ] P26j browser common + auth (≥70%)
- [x] P26k browser board + indeed (≥70%) — PR #22
- [x] P26l browser linkedin (≥70%) — PR #21
- [x] P26m mcp_server contracts (≥60%) — PR #23
- [ ] P26 done — total coverage ≥75%, all Accept gates green, CodeQL clean on main

## P27 — Docker migration (host Chrome + env secrets)

- [x] P27a Dockerfile, `.dockerignore`, `docker-compose.yml`
- [x] P27b `BuildProgress` + `docker_build.py` + manifest + stall status
- [x] P27c Monitor-agent docs (loop / Task / `/loop`)
- [x] P27d CDP `host.docker.internal` allowlist + tests
- [x] P27e `log_redaction.py` + bootstrap + tests
- [x] P27f Script stdout leak fixes (sync_sheets, run_scrape, exc paths)
- [x] P27g Docs: DOCKER, SECURITY, GETTING_STARTED, README, `.env.example`
- [x] P27h CI docker-build job
- [x] P27 done — full acceptance gate (Docker + redaction + ledgers)

## Reference docs

| Doc | Contents |
|-----|----------|
| docs/BUILD_STORY.md | How AgentZero was built (Cursor/Ralph/TDD) |
| docs/agentzero_job_hunter_d85b7004.plan.md | Original build plan + DAG |
| docs/COST_AND_MODELS.md | LLM cost estimates (2026-05-29) |
| docs/SCRAPING.md | Scraping, rate limits, OAuth, scripts |
| docs/SECURITY.md | Secrets, OAuth scopes, SSRF, LLM data, Docker, log redaction |
| docs/DOCKER.md | Optional Docker runs, host CDP, build progress |
| docs/PUBLIC_RELEASE_CHECKLIST.md | Pre-publish include/exclude + quality checklist |

## Pre-public release checklist

- [ ] Rotate OpenAI key and Google OAuth tokens before first public push
- [ ] `python tools/fix_encoding.py` then verify `git status` (no `.env`, `token.json`, profiles)
- [ ] `pytest -q` and `ruff check agentzero tests scripts tools` (513 tests as of P26k on main)
- [ ] `python scripts/sync_sheets.py --dry-run` then `--yes` on correct sheet ID
