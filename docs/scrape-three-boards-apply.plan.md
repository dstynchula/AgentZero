# Three-board scrape, apply links, and job card UX

## Mission

Operators scrape only **Indeed, LinkedIn, and Glassdoor** (Playwright/CDP). Listings without a usable **company name** and minimal **role context** never enter SQLite. Each job stores optional **`apply_url`** / **`easy_apply_url`** (when discoverable). The job detail card always offers an **Apply** action (opens `apply_url` or falls back to `job.url` with copy like **“(easy apply link not located)”** when no dedicated apply link was found), plus a clearer **Notes** section. JobSpy/Google/ZipRecruiter code paths are removed from the production stack.

## Task ledger

| ID | Summary | Status |
|----|---------|--------|
| P40a | Three-board-only factory, config defaults, web source catalog + tests | done |
| P40b | Delete JobSpy modules; update README/SCRAPING/smoke/cost tests | done |
| P40c | Listing quality gate in validate.py + pipeline tests | done |
| P41a | JobPosting apply_url fields + detail/list extraction + tests | done |
| P41b | Job card Apply buttons with posting fallback + hint copy | done |
| P42 | Job card Notes section (textarea card) | done |

## Key files

- `agentzero/scrape/factory.py` — three browser boards only
- `agentzero/scrape/validate.py` — `reject_incomplete_raw`, `has_min_role_context`
- `agentzero/scrape/apply_links.py` — apply URL extraction (SSRF-safe)
- `agentzero/models.py` — `apply_url`, `easy_apply_url`, `easy_apply`
- `agentzero/web/templates/job_card.html` — Apply + Notes UX

## Accept commands

```text
pytest tests/scrape/test_factory.py tests/test_web_sources.py tests/scrape/test_validate.py tests/scrape/test_apply_links.py tests/test_web_job_card.py tests/test_docs_web.py -q
ruff check agentzero tests scripts tools
```
