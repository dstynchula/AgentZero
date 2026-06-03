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

## P28 — Docker web job tracker (list + edit + soft-reject)

- [x] P28a Web config + optional extra
- [x] P28b Job list presenter + reject filter
- [x] P28c Read-only app + filter toggle
- [x] P28d Mutation service (status, notes, reject — no hard delete)
- [x] P28e Write routes + Nope button
- [x] P28f Docker Compose web service
- [x] P28g Docs + security note
- [x] P28h P28 acceptance gate
- [x] P28 done — web UI; rejected hidden by default; Sheets optional

## P29 — Web UI advanced display (sort, truncate, job card)

- [x] P29a Display helpers (truncate + sort)
- [x] P29b List API sort + table row shaping
- [x] P29c Sortable truncated table
- [x] P29d Job card detail page
- [x] P29e Docs + P29 gate
- [x] P29 done — sort, truncate, job card on :8080

## P30 — Docker incremental build cache

- [x] P30a Dockerfile layer reorder + pip cache mount
- [x] P30b `docker_build.py` BuildKit env
- [x] P30c CI `DOCKER_BUILDKIT=1`
- [x] P30d `docker-compose.override.yml.example` + gitignore
- [x] P30e Docs + tests + P30 gate
- [x] P30 done — code-only edits skip pip/Playwright; optional bind-mount override

## P31 — Remove Google Sheets; local web tracker only

- [x] P31a Remove `agentzero/google/`, sheet scripts, config fields
- [x] P31b Leads/MCP/scripts — approve-only commit; `rank_jobs.py`
- [x] P31c `TRACKER_UI_COLUMNS`; tracker_fields rename
- [x] P31d Docs, compose, Dockerfile, `.env.example`, AGENTS.md
- [x] P31e Tests + P31 gate
- [x] P31 done — SQLite + web UI on :8080; no gspread/OAuth

## P32 — Web UI settings, dark mode, polish (2026-06-02)

- [x] P32a Operator config (`web_operator_config.json`) + source toggles
- [x] P32b Settings page (`/config`): sources, background scrape, CDP instructions
- [x] P32c Shared layout + dark mode (localStorage) + jobs/card restyle
- [x] P32d Tests + docs mention
- [x] P32e Search title selection, dark default, CDP Connect, source-aware host hints
- [x] P32f Load résumé button (LLM search profile + title selection)
- [x] P32g Cross-platform CDP launch (py/sh/ps1) + GETTING_STARTED + Settings UI instructions
- [x] P32h Docker CDP Connect — host proxy (9222→9223), Host header rewrite, compose `web` CDP env, stale-proxy cleanup

## P33 — Search titles: résumé load fix + add/remove (2026-06-02)

- [x] P33a Writable `data/search_profile.json` (+ legacy resume fallback)
- [x] P33b Docker/docs for profile path
- [x] P33c Add/remove title API + operator merge logic
- [x] P33d Settings UI add/remove
- [x] P33e Ledger + gate

## P34 — Web UI/UX spike (2026-06-02)

Plan: [docs/web-ui-ux-spike.plan.md](docs/web-ui-ux-spike.plan.md)

- [x] P34a Source catalog: CDP boards listed last
- [x] P34b Defaults: LinkedIn-only browser boards (CDP off by default)
- [x] P34c Hide Chrome CDP card when no CDP source enabled
- [x] P34d Job tracker: centered, compact table

## P35 — Job card + Scraper nav (2026-06-03)

Plan: [docs/web-job-card-nav.plan.md](docs/web-job-card-nav.plan.md)

- [x] P35a Job card shows description from DB
- [x] P35b Remove sort-by toolbar (header sort only)
- [x] P35c Settings → Scraper (/scraper + /config redirects)

## P37 — Job card cover letter + inline edits

Plan: [docs/web-job-card-cover-letter.plan.md](docs/web-job-card-cover-letter.plan.md)

- [x] P37a Cover letter core (gpt-5.5 + prompt)
- [x] P37b Job card status/notes/reject
- [x] P37c Cover letter web runner + routes
- [x] P37d Job card cover letter UI (editable pane + save + download)
- [x] P37e Docs
- [x] P37f Ledger + gate

## P38 — Web chat interface

Plan: [docs/web-chat.plan.md](docs/web-chat.plan.md)

- [x] P38a Chat SQLite store + session API
- [x] P38b Chat LLM + read-only tools
- [x] P38c Message API + HITL pending actions
- [x] P38d Chat UI (default landing)
- [x] P38e Docs
- [x] P38f Ledger + gate

## P39 — Web chat send UX

Plan: [docs/web-chat-ux.plan.md](docs/web-chat-ux.plan.md)

- [x] P39a Optimistic user echo + waiting indicator

## Reference docs

| Doc | Contents |
|-----|----------|
| docs/BUILD_STORY.md | How AgentZero was built (Cursor/Ralph/TDD) |
| docs/agentzero_job_hunter_d85b7004.plan.md | Original build plan + DAG |
| docs/COST_AND_MODELS.md | LLM cost estimates (2026-05-29) |
| docs/SCRAPING.md | Scraping, rate limits, OAuth, scripts |
| docs/SECURITY.md | Secrets, OAuth scopes, SSRF, LLM data, Docker, log redaction |
| docs/DOCKER.md | Optional Docker runs, host CDP, build progress, web UI |
| docs/web-ui-docker.plan.md | P28 web tracker plan (TDD ledger) |
| docs/web-ui-advanced-display.plan.md | P29 sort, truncate, job card plan |
| docs/docker-build-cache.plan.md | P30 Dockerfile cache layers + dev override |
| docs/remove-google-sheets.plan.md | P31 drop Sheets; web UI is the tracker |
| docs/web-ui-settings.plan.md | P32 settings page, dark mode, scrape trigger |
| docs/web-search-titles.plan.md | P33 résumé load path + add/remove titles |
| docs/web-ui-ux-spike.plan.md | P34 tracker layout + Settings CDP UX |
| docs/web-job-card-nav.plan.md | P35 job card description + Scraper routes |
| docs/web-job-card-cover-letter.plan.md | P37 cover letter + inline job card edits |
| docs/web-chat.plan.md | P38 web chat (default landing, HITL tools) |
| docs/web-chat-ux.plan.md | P39 chat send UX (optimistic echo, waiting) |
| docs/PUBLIC_RELEASE_CHECKLIST.md | Pre-publish include/exclude + quality checklist |

## Pre-public release checklist

- [ ] Rotate OpenAI key and Google OAuth tokens before first public push
- [ ] `python tools/fix_encoding.py` then verify `git status` (no `.env`, `token.json`, profiles)
- [ ] `pytest -q` and `ruff check agentzero tests scripts tools` (513 tests as of P26k on main)
- [ ] `docker compose up web` — verify tracker after a scrape + rank
