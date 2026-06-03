---
name: Scrape durability UX
overview: Stop losing multi-hour scrape work by persisting LEAD rows immediately, skipping known jobs on re-scrape, parallel batch enrich (~5 workers), and operator-driven enrich + jobs filters.
status: draft
---

# Scrape durability and selective enrich (Ralph plan)

See the full ledger in the Cursor plan file; this is the repo mirror. **Latest update:** parallel batch enrich (T05).

## Mission

**Done** when a web background scrape completes in minutes (not hours), **LEAD rows land in SQLite before any optional slow work**, re-scrapes **skip jobs already in the DB**, operators can **Enrich one job** or **Enrich selected** (parallel ~5×), and the **jobs list supports multi-field filters**.

## Parallel enrich (added per operator feedback)

| Layer | Today | Target (T05) |
|-------|--------|----------------|
| HTTP / Glassdoor / web search | Already parallel via [`run_enrich_batch`](agentzero/enrich/batch.py) (`enrich_max_concurrency`, default 6) | Keep; default **5** in docker |
| LinkedIn **browser** detail pages | **Sequential** in batch.py (“avoids profile conflicts”) | **Bounded pool** — one Playwright, up to **5 browser contexts**, `run_parallel` |
| Web UI | CLI only (`scripts/enrich_jobs.py`) | **Enrich selected** on jobs list + progress API |

**Expected speedup:** browser-bound enrich ~**5×** wall clock (not linear if LinkedIn throttles — cap documented in T07).

## Task ledger (8 tasks)

- **T01** Comp parser hardening
- **T02** Fast pipeline + early LEAD upsert (no inline detail loop)
- **T03** Skip known `job_id` on re-scrape
- **T04** Per-job Enrich button (sync)
- **T05** Parallel batch enrich + Enrich selected UI
- **T06** Jobs list filters
- **T07** Docker/docs defaults (`ENRICH_MAX_CONCURRENCY=5`, `ENRICH_BROWSER_MAX_CONCURRENCY=5`)
- **T08** Acceptance + prep-pr + babysit

Full TDD-first Accept lines, file paths, and DAG: `.cursor/plans/scrape_durability_ux_44824563.plan.md`

## Bootstrap

Append **P50 — Scrape durability** checkboxes (T01–T08) to [`PROGRESS.md`](PROGRESS.md).
