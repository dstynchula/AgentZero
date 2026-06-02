---
name: Job card description + Scraper nav
overview: Job card shows DB description; remove sort toolbar; Settings renamed to Scraper at /scraper.
status: done
---

## Mission

- Job card displays `JobPosting.description` from SQLite (empty-state placeholder when missing).
- List view: header-only sorting (sort toolbar removed).
- Operator UI labeled **Scraper** at `/scraper`; `/config` and `/api/config` redirect for bookmarks.

## Task ledger

| Id | Branch | Outcome |
|----|--------|---------|
| T01 | feat/web-P35-T01-job-description | `description` in `job_to_row`; job card always shows Description section |
| T02 | feat/web-P35-T02-remove-sort-toolbar | Removed `.sort-toolbar` / `.sort-chip` |
| T03 | feat/web-P35-T03-scraper-routes | `/scraper/*` routes + `/config` 307 redirects |
| T04 | feat/web-P35-job-card-nav | PROGRESS + WORKLOG |

## Root cause (description)

`job_card.html` gated on `job.description`, but `job_to_row()` omitted the field.
