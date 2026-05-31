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
