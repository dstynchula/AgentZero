# AgentZero build progress

Mutable checkbox ledger for the Ralph build loop. The loop re-reads this file plus the plan each
iteration. Check a box only when that task's Accept command passes. Notes under a task record blockers.

- [x] T01 Scaffold (pyproject, package, .gitignore, .env.example, PROGRESS.md, WORKLOG.md, pytest+cov, append-only test)
- [x] T02 Config (pydantic-settings)
- [x] T03 Core models (JobPosting, stable_job_id) - 100% cov
- [x] T04 Storage (SQLite idempotent upsert + quarantine) - 100% cov
- [x] T05 Resume ingest
- [x] T06 Voice ingest
- [x] T07 Source interface + RawRecord
- [x] T08 JobSpy source
- [x] T09 Validation gate (deterministic) - 100% cov
- [x] T10 Validation self-correct (LLM) + health - 100% cov
- [x] T11 Playwright/ATS + Glassdoor source
- [x] T12 Enrichment (comp.py 100% cov)
- [x] T13 LLM provider (pluggable OpenAI/Anthropic)
- [x] T14 Ranking / matcher
- [x] T15 Cover-letter generation
- [x] T16 CSV export
- [x] T17 Sheets sync
- [x] T18 Google auth + Gmail/Calendar/Drive
- [x] T19 HITL apply queue + ATS pre-fill
- [x] T20 Runtime Ralph loop + LangGraph pipeline
- [x] T21 FastMCP server
- [x] T22 Publish polish (README, LICENSE, sample fixtures)
