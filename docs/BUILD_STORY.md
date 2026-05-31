# How AgentZero Was Built: Human + LLM Co-Programming

AgentZero is an open-source, agentic job-hunting system — and also a case study in **structured
human/LLM co-programming**. The product was designed to solve a real problem (find, rank, and
track jobs at scale). The *process* used to build it is itself a reference model for agentic
engineering work.

If you're reviewing this repo as part of an application: this document explains **how** it was
made, not just **what** it does.

## The idea

Start with a résumé in `resume/`. The agent:

- Scrapes multiple job boards
- Validates and normalizes messy listings across sources
- Enriches comp, company size, and ratings
- Ranks jobs against your profile
- Mirrors matches to SQLite and an optional Google Sheet tracker
- Lets you approve leads before they land on the sheet (never auto-applies)

The builder (Dan) paired with **Cursor** and an LLM agent in a deliberate loop — not vibe-coding,
not one-shot generation.

## The co-programming stack

| Layer | Role |
|-------|------|
| **Human (Dan)** | Product intent, trade-offs, scoping questions, acceptance of plan, steering |
| **Cursor Plan mode** | Collaborative architecture: mission, stack, DAG, task ledger, acceptance criteria |
| **Cursor Agent mode** | Implementation: TDD, commits, loop execution |
| **LLM (pluggable)** | Runtime intelligence: résumé parsing, search-term inference, ranking, scrape repair |
| **Ralph loops** | Idempotent `read state → work → write state` cycles (build-time *and* runtime) |
| **TDD + pytest** | Every task has a runnable Accept command; tests gate "done" |

## Two kinds of "Ralph loop"

We use the same *pattern* at two levels:

### 1. Build loop (how the repo was constructed)

Each iteration:

1. Re-read only the **plan** + [`PROGRESS.md`](../PROGRESS.md) (never the whole codebase)
2. Pick the next unchecked task whose dependencies are met
3. Open **only that task's files** (~3 modules + tests) — small context window
4. Write the **failing test first** from the task's Acceptance line
5. Implement until green; run Accept; check the box; append to [`WORKLOG.md`](../WORKLOG.md); commit
6. Stop. Next iteration starts fresh.

This is idempotent: re-running a completed task is a no-op (tests already pass). An interrupted
task is safe to resume.

Parallel **waves** built independent tasks concurrently (config + models in early waves; scrape
+ enrich + export later), using a dependency DAG rather than a single serial queue.

See the archived plan: [`agentzero_job_hunter_d85b7004.plan.md`](agentzero_job_hunter_d85b7004.plan.md)

### 2. Runtime loops (what the finished product runs)

The application pipeline is the same shape:

```
scrape → validate → enrich → rank → (operator approves leads) → sheet sync
```

Each stage processes pending rows keyed by stable `job_id`, marks pipeline status in SQLite, and
can fan out in parallel without double-processing. Re-running the pipeline is safe.

*(Early MVP also included cover-letter generation and an HITL apply queue; those were removed in
P16 — see [`PROGRESS.md`](../PROGRESS.md).)*

## TDD as the contract between human and agent

Every build task (T01–T22) included:

- **Scoped files** — what to touch
- **Accept command** — exact pytest/ruff/coverage gate
- **Tiered coverage** — 100% on critical paths (`validate.py`, `models.py`, `db.py`, `comp.py`);
  85% repo floor; behavior-only tests for external adapters

The Accept command is the single source of truth for "done." That let the agent loop without
human line-by-line review on every file.

## Memory without context bloat

| File | Purpose |
|------|---------|
| [`PROGRESS.md`](../PROGRESS.md) | Mutable checkbox ledger — what the loop re-reads |
| [`WORKLOG.md`](../WORKLOG.md) | Append-only audit trail — written each task, never loaded back into context |
| Plan (`docs/*.plan.md`) | Architecture + task ledger — re-read each iteration |

The work log grows forever; the loop stays small.

## What shipped (high level)

- **22 tasks** from empty repo to MVP (~105 tests)
- **Scrape-heavy** multi-board sourcing (JobSpy + HTML/ATS fixtures)
- **Schema validation gate** with deterministic repair + LLM self-correction + quarantine
- **Resume-linked search terms** — re-derived from the latest résumé each run, recent roles first
- **Pluggable LLM** (OpenAI / Anthropic)
- **Lead session** — scrape to DB, operator approves, then sheet sync
- **FastMCP** server surface
- **MIT licensed**, public-repo ready

Post-MVP enhancements (search profile from résumé, UTF-8 dev tooling on Windows) followed the
same pattern: test → implement → commit.

## Why this matters for agentic work

This repo demonstrates:

1. **Scoping before coding** — Plan mode locked decisions (scrape-heavy, lead approval, TDD, Ralph loops) before a line of Python
2. **Small-context iterations** — Tasks scoped to ~3 files; plan + PROGRESS as loop memory
3. **Test-gated autonomy** — The agent could run for hours; Accept commands prevented silent drift
4. **Idempotency everywhere** — Safe to retry builds and pipeline runs
5. **Human in the loop where it counts** — Leads require approval before sheet sync; applications are manual on each board
6. **Open book** — Plan, progress, and work log are in the repo for inspection

AgentZero is both a **tool for job search** and a **reference implementation** of disciplined
LLM-assisted software development.

## Related files

- [Original build plan (archived)](agentzero_job_hunter_d85b7004.plan.md) — full architecture, DAG, task ledger
- [`PROGRESS.md`](../PROGRESS.md) — MVP (T01–T22) + post-MVP checkbox ledger (through P22+)
- [`WORKLOG.md`](../WORKLOG.md) — timestamped build history
- [Scraping & OAuth](SCRAPING.md) — Playwright Indeed, rate limits, Google OAuth, runtime scripts
- [Cost & models](COST_AND_MODELS.md) — LLM pricing and model selection
- [`README.md`](../README.md) — setup and usage
