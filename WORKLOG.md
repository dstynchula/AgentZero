# AgentZero work log

Detailed, running, WRITE-ONLY history of the build. Append only: never edit, reorder, or delete
existing lines. Distinct from PROGRESS.md (which holds mutable checkbox state). The build loop
appends entries here but never reads this file back into context.

Entry format:
  [ISO-8601 timestamp] Txx START|DONE|BLOCKED - summary
    files: ...
    accept: <command> -> <result>
    commit: <hash>            (on DONE)
    blocker: ...              (on BLOCKED)

---

[2026-05-29T08:35:00-07:00] T01 START - scaffold project skeleton + loop ledgers.

[2026-05-29T08:38:00-07:00] T01 DONE - Python 3.14 venv; pyproject (core: pydantic/pydantic-settings;
extras: dev/scrape/llm/google/graph/mcp); pytest+coverage(branch) config with per-command opt-in cov
(85% floor enforced by global done command, not addopts, so single-task runs don't false-fail);
ruff configured; PROGRESS.md seeded T01-T22; WORKLOG.md created; append-only guard test added.
Note: this environment's file writer emits UTF-16; added a one-shot converter step to normalize all
sources to UTF-8 (will re-run after future file writes).
    files: pyproject.toml, agentzero/__init__.py, .gitignore, .env.example, PROGRESS.md, WORKLOG.md,
           tests/conftest.py, tests/test_worklog_append_only.py, resume/.gitkeep, coverletters/.gitkeep,
           output/cover_letters/.gitkeep, data/.gitkeep, README.md (re-encoded)
    accept: pip install -e .[dev] && pytest -q && ruff check . -> install ok; 1 passed, 1 skipped; lint clean; import ok
    commit: T01 (this commit)


[2026-05-29T08:45:00-07:00] T02 DONE - pydantic-settings config with LLM/search/scrape/google fields; CSV list parsing; active_api_key guard.
    files: agentzero/config.py, tests/test_config.py, tools/fix_encoding.py, .gitattributes
    accept: pytest tests/test_config.py -q -> 5 passed; ruff clean
    commit: T02

[2026-05-29T08:48:00-07:00] T03 DONE - JobPosting model, ApplicationStatus, stable_job_id, RawRecord alias; 100% branch coverage.
    files: agentzero/models.py, tests/test_models.py
    accept: pytest tests/test_models.py --cov=agentzero.models --cov-branch --cov-fail-under=100 -> 10 passed, 100% cov
    commit: T03


[2026-05-29T08:55:00-07:00] T04 DONE - SQLite jobs + quarantine tables; idempotent upsert; pipeline status gating.
    accept: pytest tests/test_db.py --cov=agentzero.storage.db --cov-branch --cov-fail-under=100 -> 100% cov

[2026-05-29T08:55:00-07:00] T07 DONE - JobSource ABC + RawRecord contract.
    accept: pytest tests/scrape/test_base.py -q -> passed

[2026-05-29T08:56:00-07:00] T13 DONE - pluggable OpenAI/Anthropic LLM providers via settings.
    accept: pytest tests/test_llm.py -q -> passed


[2026-05-29T09:02:00-07:00] T09 DONE - deterministic validate/alias/salary-parse gate; batch metrics; health assert; 100% cov.
    accept: pytest tests/scrape/test_validate.py --cov=agentzero.scrape.validate --cov-branch --cov-fail-under=100


[2026-05-29T09:20:00-07:00] T10 DONE - LLM self-correct on validate gate; batch+health; validate.py 100% cov.
[2026-05-29T09:20:00-07:00] T05 DONE - resume ingest from resume/ via LLM (txt fixture; pdf/docx optional deps).
[2026-05-29T09:20:00-07:00] T06 DONE - voice profile from coverletters/ writing samples.
[2026-05-29T09:20:00-07:00] T08 DONE - JobSpy source with injectable scraper + column mapping (offline tests).


[2026-05-29T09:45:00-07:00] Wave 5-8 DONE - enrichment (comp 100% cov), CSV export, Sheets sync, rank/matcher,
cover letters, ATS+Glassdoor HTML parsers, Google wrappers, HITL apply queue, Ralph pipeline, FastMCP server, LICENSE.
    accept: pytest -q -> 101 passed; comp.py 100% branch coverage


[2026-05-29T16:58:41Z] Post-MVP P01 DONE - Build story + archived plan; README open-book section.
    files: docs/BUILD_STORY.md, docs/agentzero_job_hunter_d85b7004.plan.md, README.md

[2026-05-29T16:58:41Z] Post-MVP P02 DONE - LLM cost documentation and optimizations.
    files: docs/COST_AND_MODELS.md, agentzero/cost/, scripts/estimate_cost.py,
           agentzero/config.py (rank_description_max_chars, gpt-5-nano default),
           agentzero/ingest/search_profile.py (session cache),
           agentzero/rank/matcher.py (description truncation), .env.example

[2026-05-29T16:58:41Z] Post-MVP P03 DONE - Google OAuth wiring for Sheets.
    files: scripts/google_auth.py, agentzero/google/client.py,
           agentzero/config.py (sheet_id URL normalize), .env.example

[2026-05-29T16:58:41Z] Post-MVP P04 DONE - Anti-rate-limit scraping: Playwright Indeed + sequential JobSpy.
    files: agentzero/scrape/browser_indeed.py, agentzero/scrape/factory.py,
           agentzero/scrape/jobspy_source.py, agentzero/scrape/multi.py,
           agentzero/scrape/resilience.py, agentzero/storage/db.py (thread lock),
           docs/SCRAPING.md, tests/scrape/test_browser_scrape.py, README.md, .env.example
    note: Live scrape blocked by Indeed selector timeout / captcha in headless mode;
          AGENTZERO_SCRAPE_BROWSER_HEADLESS=false added; P06 open.

[2026-05-29T16:58:41Z] Post-MVP P05 DONE - Runtime scripts and résumé deps.
    files: scripts/smoke_test.py, pyproject.toml (python-docx, pypdf core deps)
[2026-05-29T17:30:00Z] Post-MVP P08 DONE - Interactive search targeting before each scrape run.
    files: agentzero/ingest/search_interactive.py, agentzero/ingest/search_profile.py (salary_max),
           agentzero/config.py (search_interactive, salary_min/max), scripts/smoke_test.py,
           tests/test_search_interactive.py, docs/SCRAPING.md, .env.example
    accept: pytest tests/test_search_interactive.py tests/test_search_profile.py -q -> 10 passed

[2026-05-29T18:15:00Z] Post-MVP P07 DONE - Sheets sync CLI (scripts/sync_sheets.py, agentzero/google/sync.py).
    accept: python scripts/sync_sheets.py -> synced 10 jobs to AgentZero - 2026 Job Search

[2026-05-29T18:15:00Z] Post-MVP P09 DONE - Dedicated run_scrape.py CLI; PROGRESS.md UTF-8 fix; test import mocks.
    files: scripts/run_scrape.py, tests/test_sync_scripts.py, tests/test_google.py, tests/test_llm.py
    accept: pytest -q -> 125 passed

[2026-05-29T18:15:00Z] Post-MVP P06 DONE - Live scrape validated: 10 Indeed jobs in data/agentzero.db (prior run).
    note: Indeed visible browser + user CAPTCHA required on fresh IP; DB populated and Sheets synced.

[2026-05-29T20:00:00Z] Post-MVP P10 START - Vacuum prototype: remote vs in-office work mode prompt.
    files: agentzero/ingest/work_mode.py, scripts/prototype_work_mode.py, tests/test_work_mode.py
    accept: python scripts/prototype_work_mode.py --mode remote -> trace shows United States + is_remote=True;
            pytest tests/test_work_mode.py -q -> 10 passed
    note: Not wired into search_interactive yet; validates profile -> JobSpy/Indeed params before full integration.

[2026-05-29T21:30:00Z] Post-MVP P10 DONE - Work mode prompt (remote USA vs in-office) + browser scrapers for Indeed/LinkedIn/Glassdoor.
    files: agentzero/ingest/work_mode.py, agentzero/ingest/search_interactive.py,
           agentzero/scrape/browser_common.py, browser_board.py, browser_linkedin.py, browser_glassdoor.py,
           scripts/test_browser_scrape.py, scripts/prototype_work_mode.py, tests/test_work_mode.py,
           tests/scrape/test_browser_boards.py, agentzero/scrape/factory.py, agentzero/config.py
    accept: python scripts/test_browser_scrape.py --site indeed --remote --headless -> 10 jobs;
            same linkedin -> 10 jobs; same glassdoor -> 10 jobs; pytest -q -> 159 passed
    note: Single primary query per browser board; JobSpy skips boards already on Playwright path.

[2026-05-29T22:45:00-07:00] P11 DONE - Reliable five-source scrape pipeline: no list_pages/JSON merge; primary query; CAPTCHA cap.
    files: agentzero/scrape/factory.py, agentzero/config.py, agentzero/scrape/jobspy_params.py,
           agentzero/scrape/browser_common.py, agentzero/scrape/browser_board.py,
           agentzero/scrape/resilience.py, scripts/run_scrape.py, agentzero/ingest/search_interactive.py,
           config/job_sources.json, .env.example, docs/SCRAPING.md,
           tests/scrape/test_browser_boards.py, tests/scrape/test_browser_common.py,
           tests/scrape/test_jobspy.py, tests/scrape/test_browser_scrape.py, tests/scrape/test_sources_config.py
    accept: python -m pytest -q -> 163 passed
    note: Per run = 5 sequential fetches (Indeed, LinkedIn, Glassdoor, Google, ZipRecruiter); JobSpy no longer hits browser boards.

[2026-05-30T00:00:00Z] P12 DONE - Deep enrichment stack: detail fetch, Glassdoor company lookup,
DuckDuckGo web search, parallel batch runner, careers URL verification, sheet sync from enrich_jobs.
    files: agentzero/enrich/*, scripts/enrich_jobs.py, scripts/rank_and_sync.py,
           agentzero/enrich/batch.py, tests/test_enrich_detail.py, tests/test_web_research.py
    accept: python scripts/enrich_jobs.py --limit 10 -> 46/46 enriched; pytest -q -> green

[2026-05-30T06:00:00Z] P13 DONE - Pre-public security + quality pass.
    files: agentzero/net/url_safety.py, agentzero/net/http_client.py (redirect re-validation),
           agentzero/google/auth.py (persist_credentials strips client_secret),
           agentzero/scrape/comp_filter.py, agentzero/loops/pipeline.py (settings pass-through),
           agentzero/loops/ralph.py (failure collection), scripts/sync_sheets.py (--yes),
           scripts/prune_db_from_sheet.py, docs/SECURITY.md, .github/workflows/ci.yml,
           tests/test_http_client.py, tests/test_json_util.py, tests/test_loops.py
    accept: pytest -q -> 206 passed; ruff check agentzero tests scripts tools -> clean
    note: Comp floor uses posted range top; prune_db syncs DB to curated sheet rows.

[2026-05-30T08:00:00Z] P14 DONE - README restructure (what it is → quick start → how to use → docs → cost);
smoke_test PII redaction; rank_and_sync --yes; browser scrape SSRF guard on final URL.
    files: README.md, PROGRESS.md, scripts/smoke_test.py, scripts/rank_and_sync.py,
           agentzero/scrape/browser_common.py, agentzero/scrape/browser_board.py
    accept: pytest -q -> 206 passed

[2026-05-30T10:00:00Z] P15 DONE - Rank prompt slimming, settings reload helper, exit codes on enrich/rank failures.
    files: agentzero/rank/matcher.py, agentzero/config.py (reload_settings),
           scripts/rank_and_sync.py, scripts/enrich_jobs.py, scripts/smoke_test.py,
           scripts/google_auth.py (masked sheet id), tests/test_matcher.py, tests/test_config.py
    accept: pytest -q -> 208 passed; ruff clean

[2026-05-30T12:00:00Z] P16 DONE - Browser session integration: Chrome channel, CDP attach, cookie import.
    files: agentzero/scrape/browser_session.py, agentzero/scrape/browser_common.py (launch/close),
           agentzero/config.py, scripts/import_browser_cookies.py, scripts/cdp_browser_spike.py,
           docs/SCRAPING.md, docs/SECURITY.md, tests/scrape/test_browser_session.py,
           tests/scrape/test_launch_browser.py
    accept: pytest tests/scrape -q -> 13 passed; ruff clean

[2026-05-31T17:10:00Z] P17 DONE - Reliable browser sessions (TDD Ralph): login vs CAPTCHA split,
    SessionState classifier, verify_browser_session.py, wait_for_login status, open_glassdoor_browser,
    scrape_session_preflight, Chrome channel default in .env.example.
    files: browser_glassdoor.py, browser_linkedin.py, browser_auth.py, browser_session.py,
           session_probe.py, browser_board.py, scripts/verify_browser_session.py,
           scripts/open_glassdoor_browser.py, tests/fixtures/glassdoor_*.html, tests/scrape/*
    accept: pytest -q -> 238 passed; ruff clean
    live: verify linkedin exit 1 (authwall/login_required); verify glassdoor exit 2 (Cloudflare blocked)

[2026-05-31T19:30:00Z] P18 DONE - Conversational lead-gathering session: LEAD status lifecycle,
    shared orchestration module, MCP + CLI front-ends, sheet date_applied auto-promotion, tracker import optimization.
    files: agentzero/models.py (ApplicationStatus.LEAD),
           agentzero/leads/session.py, agentzero/leads/__init__.py,
           agentzero/loops/pipeline.py (new_status, _merge_scrape_job),
           agentzero/rank/export_filter.py (exclude LEAD from sheet),
           agentzero/apply/sheet_fields.py (PRE_APPLICATION_STATUSES, date_applied promotion),
           agentzero/apply/tracking.py (_JobIndex, import_tracker_rows dry_run),
           agentzero/mcp_server.py (suggest_targets, run_scrape, list/approve/reject/commit_leads),
           scripts/run_lead_session.py, scripts/run_scrape.py (remove stale voice= arg),
           scripts/launch_chrome_cdp.ps1 (dedicated profile for Chrome 136+ CDP),
           scripts/import_sheet_status.py (single DB connection, dry_run preview),
           agentzero/scrape/remote_policy.py (dead branch cleanup),
           tests/test_leads_session.py, tests/test_export_filter.py, tests/test_application_tracking.py,
           README.md, docs/SCRAPING.md, PROGRESS.md
    accept: pytest -q -> 271 passed; ruff check agentzero tests scripts -> clean
    note: Lead flow = scrape/rank into status=lead (DB only) → operator approves → NEW + sheet sync.
          MCP server registered as python -m agentzero.mcp_server --stdio for Cursor agent chat flow.
          Classic run_scrape.py unchanged (writes NEW directly for automation).
    live: full scrape via run_scrape.py after CDP fix; Indeed+Glassdoor sessions ready on dedicated profile.

[2026-05-31T22:00:00Z] P19 DONE - Parser hardening + enrichment fixes after first live lead sessions.
    LinkedIn SPA parser (embedded Voyager JSON, company from subtitle/logo alt, comp from formattedSalary);
    pipeline LinkedIn detail fetch for missing comp; Glassdoor Unknown→company resolver for partner listing URLs;
    backfill CLIs for LinkedIn comp and Glassdoor companies; Glassdoor rating refresh via DuckDuckGo when HTTP blocked.
    files: agentzero/scrape/browser_linkedin.py, agentzero/scrape/glassdoor_company.py,
           agentzero/scrape/browser_glassdoor.py, agentzero/enrich/detail_parse.py, agentzero/enrich/detail_fetch.py,
           agentzero/enrich/gaps.py, agentzero/loops/pipeline.py, agentzero/enrich/glassdoor_company.py,
           scripts/run_linkedin_lead_scrape.py, scripts/backfill_linkedin_comp.py,
           scripts/backfill_glassdoor_companies.py, tests/scrape/test_glassdoor_company.py,
           tests/fixtures/linkedin_search_*.html, tests/fixtures/glassdoor_job_listing_slug.html,
           PROGRESS.md, WORKLOG.md, docs/SCRAPING.md, docs/agentzero_job_hunter_d85b7004.plan.md, README.md
    accept: pytest -q -> 285 passed; ruff check agentzero tests scripts -> clean
    note: Direct Glassdoor HTTP often returns 403; enrich_jobs uses DuckDuckGo company research as fallback.
          LinkedIn lead scrapes require CDP Chrome (launch_chrome_cdp.ps1). Removed temp debug scripts/data files.
    live: 39 rows on AgentZero - 2026 Job Search; 0 Unknown companies; 38/39 with Glassdoor ratings after refresh.

[2026-05-31T23:30:00Z] P20 DONE - MCP interactive workflow, CDP auto-launch, security hardening.
    MCP instructions + lead_session_workflow; .cursor/mcp.json + AGENTS.md + Cursor rule for chat-first sessions;
    ensure_cdp_ready auto-starts Chrome when CDP down; localhost-only CDP URL validation; HTTP 2MB cap;
    MCP scrape/commit input bounds; commit_leads accurate approved count; token file permissions; CI permissions.
    files: agentzero/mcp_server.py, agentzero/mcp/*, agentzero/scrape/browser_common.py, agentzero/net/cdp_safety.py,
           agentzero/net/http_client.py, agentzero/config.py, agentzero/google/auth.py, agentzero/leads/session.py,
           .cursor/mcp.json, .cursor/rules/agentzero-mcp.mdc, AGENTS.md, docs/SECURITY.md, docs/SCRAPING.md,
           README.md, .env.example, .github/workflows/ci.yml, tests/test_cdp_safety.py, tests/test_mcp_validation.py,
           tests/test_http_client.py, tests/scrape/test_launch_browser.py, PROGRESS.md, WORKLOG.md
    accept: pytest -q -> 293 passed; ruff check agentzero tests scripts -> clean

[2026-06-01T00:00:00Z] P21 DONE - Pre-review cleanup from senior code-review pass.
    SECURITY.md aligned with P16 pipeline (no cover-letter/HITL refs); enrichment vs scrape SSRF scope;
    LLM untrusted-input section; session-probe post-nav guard; removed dead BrowserIndeedSource (~130 lines);
    factory raises ValueError when no scrape sources; Windows token ACL via icacls; list_pages marked example-only.
    files: docs/SECURITY.md, docs/agentzero_job_hunter_d85b7004.plan.md, agentzero/scrape/session_probe.py,
           agentzero/scrape/factory.py, agentzero/scrape/browser_indeed.py, agentzero/scrape/sources_config.py,
           agentzero/scrape/parse_list.py, agentzero/google/auth.py, tests/scrape/test_session_probe.py,
           tests/scrape/test_browser_scrape.py, tests/scrape/test_location.py, tests/test_google_auth_scopes.py,
           PROGRESS.md, WORKLOG.md
    accept: pytest -q -> 304 passed; ruff check agentzero tests scripts tools -> clean

[2026-06-01T01:00:00Z] P22 DONE - Export filter fix + doc alignment from second code review.
    REJECTED leads no longer export to sheet; filter_jobs_for_export always applies LEAD/REJECTED gates;
    MCP commit_leads notes full worksheet rewrite; BUILD_STORY/.env.example/smoke_test updated for P16 scope.
    files: agentzero/rank/export_filter.py, agentzero/mcp_server.py, tests/test_export_filter.py,
           tests/test_leads_session.py, docs/BUILD_STORY.md, .env.example, scripts/smoke_test.py, PROGRESS.md
    accept: pytest -q -> 307 passed; ruff check agentzero tests scripts tools -> clean

[2026-06-01T02:00:00Z] P23 DONE - Polish nits from final code review pass.
    format_lead_preview escapes pipe chars; is_application_locked doc clarifies prune vs export;
    MCP workflow + SECURITY lead-status notes; consolidated mcp_server imports; llm provider indent fix.
    files: agentzero/leads/session.py, agentzero/apply/tracking.py, agentzero/mcp/workflow.py,
           agentzero/mcp_server.py, agentzero/llm/provider.py, agentzero/rank/export_filter.py,
           docs/SECURITY.md, docs/BUILD_STORY.md, docs/agentzero_job_hunter_d85b7004.plan.md,
           tests/test_leads_session.py, tests/test_application_tracking.py, PROGRESS.md
    accept: pytest -q -> 309 passed; ruff check agentzero tests scripts tools -> clean

[2026-05-31T16:15:00-07:00] P24 DONE - Public launch polish for portfolio-ready first impression.
    README now has architecture-at-a-glance, design tradeoffs, and quality bar; added dedicated
    docs/PUBLIC_RELEASE_CHECKLIST.md with include/exclude guidance; linked checklist in README.
    files: README.md, docs/PUBLIC_RELEASE_CHECKLIST.md, PROGRESS.md, WORKLOG.md
    accept: pytest -q -> 309 passed; ruff check agentzero tests scripts tools -> clean

[2026-05-31T16:25:00-07:00] P25 DONE - WORKLOG append-only guard made encoding-robust on Windows.
    test_worklog_append_only now reads git bytes and decodes UTF-8 explicitly (no locale mismatch).
    files: tests/test_worklog_append_only.py, PROGRESS.md, WORKLOG.md
    accept: pytest -q -> 309 passed; ruff check agentzero tests scripts tools -> clean

[2026-06-01T04:24:00Z] P26-0 DONE - CI reports branch coverage; P26 ledger seeded in PROGRESS.md.
    Pytest step now runs --cov=agentzero --cov-branch --cov-report=term-missing:skip-covered (report-only).
    files: .github/workflows/ci.yml, PROGRESS.md
    accept: PR #6 merged; CI green on main (77d97fe)

[2026-06-01T04:30:00Z] P26a DONE - agentzero.net branch coverage 77% → 98%.
    Expanded url_safety (DNS mocks, url_host_matches), http_client edge paths, cdp_safety validation.
    files: tests/test_url_safety.py, tests/test_http_client.py, tests/test_cdp_safety.py
    accept: pytest tests/test_url_safety.py tests/test_http_client.py tests/test_cdp_safety.py --cov=agentzero.net --cov-branch --cov-fail-under=90; PR #7 merged (c470203)

[2026-06-01T05:00:00Z] P26b DONE - agentzero.mcp branch coverage 71% → 100%.
    Expanded validation edge cases; added workflow text tests for lead_session_workflow_text().
    files: tests/test_mcp_validation.py, tests/test_mcp_workflow.py
    accept: pytest tests/test_mcp_validation.py tests/test_mcp_workflow.py --cov=agentzero.mcp --cov-branch --cov-fail-under=85; PR #10 merged (4a5a29b)

[2026-06-01T05:15:00Z] P26c DONE - agentzero.leads.session branch coverage 54% → 98%.
    Mocked suggest_targets, build_run_settings, check_board_sessions, run_lead_scrape, commit_leads, preview helpers.
    files: tests/test_leads_session.py
    accept: pytest tests/test_leads_session.py --cov=agentzero.leads --cov-branch --cov-fail-under=75; PR #13 merged (c49df1e)

[2026-06-01T05:30:00Z] P26d DONE - agentzero.apply + export_filter branch coverage 70% → 95%.
    Added test_apply_sheet_fields; extended application_tracking and export_filter tests.
    files: tests/test_apply_sheet_fields.py, tests/test_application_tracking.py, tests/test_export_filter.py
    accept: pytest tests/test_application_tracking.py tests/test_export_filter.py tests/test_apply_sheet_fields.py --cov=agentzero.apply --cov=agentzero.rank.export_filter --cov-branch --cov-fail-under=90; PR #15 merged (4427fe7)

[2026-06-01T05:35:00Z] P26e DONE - enrich I/O branch coverage ≥75%.
    Mocked HTTP, file I/O, and enrichment paths in new test_enrich_io module.
    files: tests/test_enrich_io.py
    accept: pytest tests/test_enrich_io.py --cov=agentzero.enrich --cov-branch --cov-fail-under=75; PR #17 merged (cf8e0f4)

[2026-06-01T05:40:00Z] P26f DONE - pipeline orchestration branch coverage → 93%.
    Extended test_loops with mocked scrape/enrich/rank stages and error branches.
    files: tests/test_loops.py
    accept: pytest tests/test_loops.py --cov=agentzero.loops --cov-branch --cov-fail-under=75; PR #18 merged (7c278af)

[2026-06-01T05:45:00Z] P26g DONE - google import/sync branch coverage ≥75%.
    Sheet import, prune_sync, and sync script tests with mocked credentials and API clients;
    CI fix: patch builtins.__import__ for credential ImportError path; ruff cleanup on test_sync_scripts.
    files: tests/test_sheet_import.py, tests/test_prune_sync.py, tests/test_sync_scripts.py
    accept: pytest tests/test_sheet_import.py tests/test_prune_sync.py tests/test_sync_scripts.py --cov=agentzero.google --cov-branch --cov-fail-under=75; PR #19 merged (ea8f4bb)

[2026-06-01T05:50:00Z] P26h DONE - scrape factory + session branch coverage ≥70%.
    Expanded browser_session, session_probe, session_health, and factory/multi tests in scrape suite;
    CI fix: move mid-file imports to top (ruff E402) in test_browser_scrape.py, test_browser_session.py, test_session_probe.py.
    files: tests/scrape/test_browser_scrape.py, tests/scrape/test_browser_session.py, tests/scrape/test_session_probe.py, tests/scrape/test_session_health.py
    accept: pytest tests/scrape/test_browser_scrape.py tests/scrape/test_browser_session.py tests/scrape/test_session_probe.py --cov=agentzero.scrape --cov-branch; PR #20 merged (db01e75)

[2026-06-01T06:00:00Z] P26 open PRs - CI unblocked on browser_linkedin (#21), browser_board/indeed (#22), mcp_server (#23).
    Same ruff E402/I001 pattern as P26h: module-level imports moved to file tops; merged main into #21/#22
    (kept tier-specific tests + P26h factory coverage); #23 import sort via ruff --fix. All three PRs CI green.
    files: tests/scrape/test_browser_scrape.py, tests/scrape/test_browser_boards.py, tests/scrape/test_indeed_block_detection.py, tests/test_mcp.py
    accept: gh pr checks 21/22/23 -> test + CodeQL pass (pending squash merge)

[2026-06-01T06:15:00Z] P26l DONE - browser_linkedin branch coverage ≥70%.
    TestLinkedInBrowserParse in test_browser_scrape (fixtures + inline HTML); merged main after P26h;
    ruff E402 import reorder; CI retrigger via empty commit.
    files: tests/scrape/test_browser_scrape.py
    accept: pytest tests/scrape/test_browser_scrape.py --cov=agentzero.scrape.browser_linkedin --cov-branch --cov-fail-under=70; PR #21 merged (734a0e6)

[2026-06-01T06:20:00Z] P26m DONE - mcp_server tool handlers branch coverage ≥60%.
    Mocked FastMCP tool registration and handler paths in test_mcp; ruff I001 import sort.
    files: tests/test_mcp.py
    accept: pytest tests/test_mcp.py --cov=agentzero.mcp_server --cov-branch --cov-fail-under=60; PR #23 merged (438dbed)

[2026-06-01T06:30:00Z] P26k - merge conflict resolved on PR #22 (browser_board + browser_indeed).
    After #21/#23 landed on main, test_browser_scrape.py conflicted: kept P26k Indeed tests and main's
    TestLinkedInBrowserParse; consolidated linkedin imports at file top. PR mergeable; CI green (0122cb6).
    files: tests/scrape/test_browser_boards.py, tests/scrape/test_browser_scrape.py, tests/scrape/test_indeed_block_detection.py
    accept: gh pr checks 22 -> test + CodeQL pass; squash merge pending

[2026-06-01T06:45:00Z] P26k DONE - browser_board + browser_indeed branch coverage ≥70%.
    Mocked BrowserJobBoardSource fetch; Indeed mosaic/DOM/consent/session tests; block-detection in test_indeed_block_detection;
    merged main twice (LinkedIn + mcp_server) with conflict resolution in test_browser_scrape.
    files: tests/scrape/test_browser_boards.py, tests/scrape/test_browser_scrape.py, tests/scrape/test_indeed_block_detection.py
    accept: pytest tests/scrape/test_browser_boards.py tests/scrape/test_browser_scrape.py tests/scrape/test_indeed_block_detection.py --cov=agentzero.scrape.browser_board --cov=agentzero.scrape.browser_indeed --cov-branch --cov-fail-under=70; PR #22 merged (629f059)

[2026-06-02T12:00:00Z] P27a START - Docker migration: container foundation (Dockerfile, compose, ignore).
    files: (pending)
    accept: (pending)

[2026-06-02T18:00:00Z] P27 DONE - Docker migration (host Chrome CDP + env secrets + build ETA + log redaction).
    files: Dockerfile, .dockerignore, docker-compose.yml, docker/build.manifest.json,
           scripts/docker_build.py, scripts/docker_build.ps1, agentzero/loops/progress.py (BuildProgress),
           agentzero/log_redaction.py, agentzero/net/cdp_safety.py, agentzero/config.py, agentzero/__init__.py,
           scripts/sync_sheets.py, scripts/run_scrape.py, agentzero/scrape/browser_board.py,
           tests/test_build_progress.py, tests/test_log_redaction.py, tests/test_cdp_safety.py, tests/test_config.py,
           tests/test_sync_scripts.py, docs/DOCKER.md, docs/SECURITY.md, docs/GETTING_STARTED.md, README.md,
           .env.example, .gitignore, .github/workflows/ci.yml, PROGRESS.md
    accept: pytest -q && ruff check agentzero tests scripts tools -> all green (532 tests)

[2026-06-02T20:00:00Z] P28 DONE - Docker web job tracker (list, status/notes edit, soft-reject).
    files: agentzero/web/, tests/test_web_*.py, tests/test_docker_compose_web.py, tests/test_docs_web.py,
           docker-compose.yml (web service), Dockerfile ([web] extra), pyproject.toml, agentzero/config.py,
           docs/DOCKER.md, docs/SECURITY.md, docs/web-ui-docker.plan.md, .github/workflows/ci.yml, PROGRESS.md
    accept: pytest tests/test_web_*.py tests/test_docker_compose_web.py tests/test_docs_web.py -q -> 26 passed;
            ruff check agentzero/web tests/test_web*.py -> clean
    branch: feat/web-P28-docker-ui

[2026-06-02T21:30:00Z] P29 DONE - Web UI advanced display (sort, truncate, job card).
    files: agentzero/web/display.py, agentzero/web/jobs.py, agentzero/web/app.py,
           agentzero/web/templates/jobs.html, agentzero/web/templates/job_card.html,
           tests/test_web_display.py, tests/test_web_jobs.py, tests/test_web_app_detail.py,
           tests/test_web_app_read.py, docs/DOCKER.md, docs/web-ui-advanced-display.plan.md, PROGRESS.md
    accept: pytest tests/test_web_*.py -q && ruff check agentzero/web -> green
    branch: feat/web-P29-advanced-display

[2026-06-02T22:00:00Z] P30 DONE - Docker incremental build cache (layer order, BuildKit pip mount, dev override).
    files: Dockerfile, scripts/docker_build.py, .github/workflows/ci.yml,
           docker-compose.override.yml.example, .gitignore, docs/DOCKER.md,
           docs/docker-build-cache.plan.md, tests/test_dockerfile_cache.py, tests/test_docs_web.py, PROGRESS.md
    accept: pytest tests/test_dockerfile_cache.py tests/test_docs_web.py -q; ruff clean
    branch: feat/docker-P30-build-cache

[2026-06-02T23:00:00Z] P31 DONE - Remove Google Sheets; local web tracker only.
    files: (removed agentzero/google/, sync_sheets.py, google_auth.py, rank_and_sync.py, …),
           agentzero/apply/tracker_fields.py, scripts/rank_jobs.py, agentzero/leads/session.py,
           agentzero/mcp_server.py, docs/README/GETTING_STARTED/SCRAPING/SECURITY/DOCKER, PROGRESS.md
    accept: pytest -q && ruff check agentzero tests scripts tools -> green
    branch: feat/P31-remove-google-sheets

[2026-06-02T23:45:00Z] P32 DONE - Web UI settings page, dark mode, operator source config.
    Settings at /config: enable/disable five sources (saved to data/web_operator_config.json),
    background scrape button (threaded run_lead_scrape), CDP status + launch_chrome_cdp.ps1 hints.
    Shared base.html layout with dark/light theme toggle; jobs list and job card restyled.
    files: agentzero/web/operator_config.py, sources.py, cdp_status.py, scrape_runner.py,
           agentzero/web/app.py, agentzero/web/templates/base.html, config.html, jobs.html, job_card.html,
           tests/test_web_operator_config.py, tests/test_web_sources.py, tests/test_web_app_config.py,
           docs/DOCKER.md, docs/web-ui-settings.plan.md, PROGRESS.md
    accept: pytest tests/test_web_*.py -q; ruff check agentzero/web -> green

[2026-06-02T23:55:00Z] P32e DONE - Settings: search title checkboxes, dark mode default, CDP Connect retry, dynamic host hints.
    files: agentzero/web/search_titles.py, cdp_status.py, operator_config.py, app.py, templates/config.html, base.html,
           tests/test_web_search_titles.py, tests/test_web_cdp_status.py, tests/test_web_app_config.py, PROGRESS.md
    accept: pytest tests/test_web_*.py -q; ruff check agentzero/web -> green

[2026-06-02T24:05:00Z] P32f DONE - Settings Load résumé button; background LLM search profile; web compose mounts resume/.
    files: agentzero/web/resume_loader.py, app.py, templates/config.html, docker-compose.yml,
           tests/test_web_resume_loader.py, tests/test_web_app_config.py, docs/DOCKER.md, PROGRESS.md
    accept: pytest tests/test_web_resume_loader.py tests/test_web_app_config.py -q; ruff clean

[2026-06-02T24:15:00Z] P32g DONE - Cross-platform CDP Chrome launch + operator instructions (GETTING_STARTED + Settings).
    scripts/launch_chrome_cdp.py, launch_chrome_cdp.sh; PS1 wraps Python; agentzero/scrape/cdp_launch.py
    browser_common.launch_cdp_chrome uses shared module; cdp_status launch_commands + config.html Step 1/2
    docs: GETTING_STARTED, SCRAPING, DOCKER, .env.example; tests/test_cdp_launch.py, test_docs_web, test_web_cdp_status
    accept: pytest tests/test_cdp_launch.py tests/test_web_cdp_status.py tests/test_docs_web.py tests/test_web_app_config.py -q; ruff clean

[2026-06-02T22:45:00Z] P32h DONE - Docker CDP Connect: host proxy, Host rewrite, web compose env.
    agentzero/scrape/cdp_host_proxy.py forwards 0.0.0.0:9222 -> Chrome 127.0.0.1:9223; rewrites Host/Origin
    for host.docker.internal; stop stale proxies on relaunch; web service CDP env + Connect probe-only in Docker.
    files: cdp_host_proxy.py, cdp_launch.py, cdp_status.py, docker-compose.yml, docs/DOCKER.md, GETTING_STARTED.md,
           README.md, .env.example, tests/test_cdp_host_proxy.py, tests/test_cdp_launch.py, tests/test_web_cdp_status.py
    accept: pytest tests/test_cdp_host_proxy.py tests/test_cdp_launch.py tests/test_web_cdp_status.py -q; ruff clean

[2026-06-02T23:30:00Z] P33 DONE - Search titles: résumé load fix + add/remove in Settings.
    data/search_profile.json beside DB (Docker resume/ stays ro); legacy resume/ snapshot fallback.
    Settings: Add title, Remove per row, Save titles preserves custom; POST add/remove routes.
    files: agentzero/ingest/search_profile.py, agentzero/web/search_titles.py, app.py, config.html,
           docs/DOCKER.md, GETTING_STARTED.md, SCRAPING.md, README.md, tests/test_search_profile.py,
           tests/test_web_search_titles.py, tests/test_web_app_config.py, tests/test_docs_web.py, PROGRESS.md
    accept: pytest -q && ruff check agentzero tests scripts tools -> green
    branch: feat/web-P33-search-titles

[2026-06-03T00:00:00Z] P33 merged — squash to main 1167185. PR: https://github.com/dstynchula/AgentZero/pull/33

[2026-06-03T12:00:00Z] P34 DONE - Web UI/UX spike: CDP sources last in Settings catalog; linkedin-only browser defaults;
    hide Chrome CDP card when unused; centered compact job tracker table.
    files: agentzero/web/sources.py, agentzero/config.py, agentzero/web/templates/{config,jobs,base}.html,
           .env.example, docs/GETTING_STARTED.md, tests/test_web_sources.py, tests/test_config.py,
           tests/test_web_app_config.py, tests/test_web_app_read.py, PROGRESS.md
    accept: pytest -q && ruff check agentzero tests scripts tools -> green
    branch: feat/web-P34-ui-ux-spike
    PR: https://github.com/dstynchula/AgentZero/pull/34

[2026-06-03T18:00:00Z] P35 DONE - Job card description from DB; remove sort toolbar; Settings → Scraper (/scraper + /config redirects).
    files: agentzero/storage/csv_export.py, agentzero/web/app.py, agentzero/web/templates/{job_card,config,jobs,base}.html,
           README.md, docs/DOCKER.md, docs/GETTING_STARTED.md, docs/web-job-card-nav.plan.md,
           tests/test_web_job_card.py, tests/test_web_jobs.py, tests/test_web_app_read.py,
           tests/test_web_app_config.py, tests/test_docs_web.py, PROGRESS.md
    accept: pytest -q && ruff check agentzero tests scripts tools -> green
    branch: feat/web-P35-job-card-nav
