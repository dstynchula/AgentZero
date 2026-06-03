# Web Scraper: search targets UI

Operators configure work mode (remote USA vs in-office cities), comp floor, and
post-scrape `remote_only` on `/scraper` without CLI prompts.

## Flow

1. `POST /scraper/search-targets` → `agentzero/web/search_targets.py` validation
2. Persist `work_mode`, `locations`, `salary_min`, `scrape_remote_only` in `web_operator_config.json`
3. `apply_operator_search_targets()` in `scrape_runner._execute_scrape` when `search_targets_configured`

## Related

- Search titles: [web-search-titles.plan.md](web-search-titles.plan.md)
- Security: [SECURITY.md](SECURITY.md) (Scraper form validation)
