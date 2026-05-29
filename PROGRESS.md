# AgentZero build progress

Mutable checkbox ledger for the Ralph build loop. The loop re-reads this file plus the plan each
iteration. Check a box only when that task's Accept command passes. Notes under a task record blockers.

- [x] T01 Scaffold (pyproject, package, .gitignore, .env.example, PROGRESS.md, WORKLOG.md, pytest+cov, append-only test)
- [ ] T02 Config (pydantic-settings)
- [ ] T03 Core models (JobPosting, stable_job_id) - 100% cov
- [ ] T04 Storage (SQLite idempotent upsert + quarantine) - 100% cov
- [ ] T05 Resume ingest
- [ ] T06 Voice ingest
- [ ] T07 Source interface + RawRecord
- [ ] T08 JobSpy source
- [ ] T09 Validation gate (deterministic) - 100% cov
- [ ] T10 Validation self-correct (LLM) + health - 100% cov
- [ ] T11 Playwright/ATS + Glassdoor source
- [ ] T12 Enrichment (comp.py 100% cov)
- [ ] T13 LLM provider (pluggable OpenAI/Anthropic)
- [ ] T14 Ranking / matcher
- [ ] T15 Cover-letter generation
- [ ] T16 CSV export
- [ ] T17 Sheets sync
- [ ] T18 Google auth + Gmail/Calendar/Drive
- [ ] T19 HITL apply queue + ATS pre-fill
- [ ] T20 Runtime Ralph loop + LangGraph pipeline
- [ ] T21 FastMCP server
- [ ] T22 Publish polish (README, LICENSE, sample fixtures)
