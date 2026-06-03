# LLM cost and model selection

**Pricing snapshot date: 2026-05-29**

AgentZero uses your LLM provider for résumé parsing, search-term inference, and job
ranking. **A typical scrape-and-rank run costs cents, not dollars** — even with a
résumé-driven search across several terms and locations.

This document explains what drives cost, how to pick a model, and ballpark
estimates. Provider prices change; verify on [OpenAI](https://openai.com/api/pricing/)
or [Anthropic](https://www.anthropic.com/pricing) before budgeting.

## The short version

| Run type | Typical unique jobs ranked | gpt-5-nano | gpt-4o-mini |
|----------|---------------------------|------------|-------------|
| Quick test (`--limit 5`, few queries) | ~30–40 | **~$0.01** | ~$0.02 |
| Modest (1 term, 1 location, 50 results) | ~40–50 | **~$0.01** | ~$0.03 |
| Full résumé grid (~6 terms × 2 locations) | ~100–150 | **~$0.02–0.03** | ~$0.06–0.09 |
| Heavy day (200+ unique listings) | ~200 | **~$0.04** | ~$0.10 |

**Daily scraping for a month at the “full résumé” tier with gpt-5-nano: roughly
$0.60–$1.50/month** — not hundreds of dollars.

## What you pay for (per run)

| Step | LLM calls | Notes |
|------|-----------|--------|
| Résumé → profile | 1 | Once per script run |
| Résumé → search terms | 1 | Once per process (cached if unchanged) |
| Rank each job | **1 × unique jobs** | **Main cost** |
| Cover letter (job card) | **1 per generate** | Uses `AGENTZERO_COVER_LETTER_MODEL` (default `gpt-5.5`) |
| Validation repair | ~5% of rows | Fallback; usually small |

**Not billed by AgentZero:** JobSpy board scraping (no API key fee from us).

## Cost optimizations built in

1. **Session search-profile cache** — ingest + scrape in one command no longer
   calls the LLM twice for search terms when the résumé file is unchanged.
2. **Description truncation for ranking** — `AGENTZERO_RANK_DESCRIPTION_MAX_CHARS`
   (default `2500`) caps job text in rank prompts. Full descriptions remain in SQLite/CSV.
3. **Deterministic validation first** — LLM repair only runs when schema validation fails.
4. **Match-score export gate** — `AGENTZERO_MIN_MATCH_SCORE` (default `0.75`) keeps low-fit
   jobs out of the Google Sheet after ranking. You still pay to rank them once; they remain in
   SQLite. Set to `0` to export everything ranked.

## Model selection criteria

Pick **one** model in `.env` (`AGENTZERO_LLM_MODEL`). Set **one** API key for your
provider.

### Tier 1 — Scrape, ingest, rank (default)

**Recommended: `gpt-5-nano`**

- Cheapest OpenAI tier in this snapshot ($0.05 / 1M input, $0.40 / 1M output)
- Strong enough for JSON extraction and fit scoring
- Best default if you're between jobs and running daily

**Alternative: `gpt-4o-mini`**

- Slightly higher cost (~3× vs nano on typical runs)
- Conservative choice if JSON reliability matters more than pennies

### Cover letters (job card only)

**Default: `gpt-5.5`** via `AGENTZERO_COVER_LETTER_MODEL`

- Separate from scrape/rank model — natural tone for interview-ready drafts
- One LLM call per **Generate** on the job card (résumé + job description)
- Requires `AGENTZERO_LLM_PROVIDER=openai` and `OPENAI_API_KEY`

### Avoid for bulk ranking

- **`gpt-5.4-nano`** — tuned for ranking, but **output pricing** makes it more
  expensive than `gpt-4o-mini` on multi-job runs in our estimates
- **Large / reasoning models** (`gpt-5.4`, `gpt-5.2`, etc.) — overkill for structured JSON

### Anthropic

`AGENTZERO_LLM_PROVIDER=anthropic` with a **Haiku** model is comparable to
gpt-4o-mini in cost — fine, but not the cheapest option for high-volume ranking.

## Pricing table (2026-05-29 snapshot)

USD per 1 million tokens:

| Model | Input | Output | Good for |
|-------|-------|--------|----------|
| gpt-5-nano | $0.05 | $0.40 | **Default** — ingest, search, rank |
| gpt-4.1-nano | $0.10 | $0.40 | Same tier; deprecating |
| gpt-4o-mini | $0.15 | $0.60 | Safe all-in-one default |
| gpt-5.4-nano | $0.20 | $1.25 | Classification/ranking (not cheapest bulk) |
| gpt-4.1-mini | $0.40 | $1.60 | Higher-quality rank if needed |
| gpt-5.4-mini | $0.75 | $4.50 | Higher-quality letters |

## Estimate for your `.env`

From the repo root (venv active):

```powershell
python scripts/estimate_cost.py
```

Override job count:

```powershell
python scripts/estimate_cost.py --jobs 120
python scripts/estimate_cost.py --model gpt-5-nano
```

## Knobs that change cost

| Knob | Effect |
|------|--------|
| `AGENTZERO_RESULTS_WANTED` | More rows per search query |
| Résumé-derived `search_terms` × `locations` | More queries → more unique jobs |
| `AGENTZERO_RANK_DESCRIPTION_MAX_CHARS` | Lower = cheaper rank calls |
| Re-running pipeline on already-ranked jobs | Idempotent — no re-rank if status is `done` |
## Example `.env` (budget-conscious)

```env
AGENTZERO_LLM_PROVIDER=openai
AGENTZERO_LLM_MODEL=gpt-5-nano
OPENAI_API_KEY=sk-...

AGENTZERO_RESULTS_WANTED=30
AGENTZERO_RANK_DESCRIPTION_MAX_CHARS=2500
```

If search terms aren't résumé-derived yet, set explicit terms/locations to limit
query fan-out:

```env
AGENTZERO_SEARCH_TERMS=Staff Security Engineer,Principal Security Engineer
AGENTZERO_LOCATIONS=Remote,Los Angeles
```

## Disclaimer

Estimates assume typical résumé and JobSpy payload sizes. Long descriptions,
many search queries, or re-ranking already-processed rows after a DB reset can
increase cost. **Still on the order of cents to low tens of cents per run** for
sensible settings — not “a million dollars.”
