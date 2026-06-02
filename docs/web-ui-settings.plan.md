---
name: Web UI Settings + Dark Mode
overview: "Settings page for sources, scrape trigger, CDP instructions; shared dark theme."
status: done
branch_prefix: feat/web-
---

## Mission

Operators configure the five-source stack, kick off background scrapes, and see CDP setup steps
from http://localhost:8080 — without editing `.env` for every source toggle.

## Delivered (P32)

| Item | Path |
|------|------|
| Operator overlay | `data/web_operator_config.json` via `agentzero/web/operator_config.py` |
| Settings UI | `GET /config`, `POST /config/sources`, `POST /config/scrape` |
| CDP status | `agentzero/web/cdp_status.py` (reachable probe + hints) |
| Background scrape | `agentzero/web/scrape_runner.py` → `run_lead_scrape` (status=lead) |
| Theme | `templates/base.html` — CSS variables + localStorage |
| API | `GET /api/config` |

## Out of scope (later)

- Sheet/card UI refinements (user follow-up)
- In-container CDP Chrome launch (host-only by design)
- Web auth
