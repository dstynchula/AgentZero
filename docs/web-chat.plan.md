# P38 — Web chat interface (default landing)

**Status:** complete on branch `feat/web-P38-chat`

Operators open http://localhost:8080 and land on a chat UI. The assistant reads the SQLite job tracker and résumé/search profile, discusses fit, and proposes actions with **Confirm/Reject** before mutations or scrapes (same trust model as MCP lead sessions).

## Locked decisions

| Decision | Choice |
|----------|--------|
| Default route | `GET /` → chat; job list at `GET /jobs` |
| Nav | Chat \| Jobs \| Scraper |
| History | SQLite in `data/agentzero.db` — `chat_sessions`, `chat_messages`, `chat_pending_actions` |
| Mutations | Full tool set with HITL pending actions |
| LLM | `AGENTZERO_CHAT_MODEL` (default `gpt-5.5`); OpenAI tool-calling v1 |
| Tool implementation | Existing Python modules (not HTTP self-calls) |
| Streaming | v1 non-streaming JSON |

## Tasks

- [x] P38a Chat SQLite store + session API
- [x] P38b Chat LLM + read-only tools
- [x] P38c Message API + HITL pending actions
- [x] P38d Chat UI (default landing)
- [x] P38e Docs
- [x] P38f Ledger + gate
