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

