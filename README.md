# AgentZero

Resume-driven, open-source job-hunting agent: multi-board sourcing, enrichment, ranking,
voice-matched cover letters, and a human-in-the-loop application tracker.

## Windows development (UTF-8)

PowerShell can default to UTF-16 for `Out-File` / `Set-Content`, which breaks Python, TOML,
and git diffs. Before editing files in this repo, set UTF-8 for the session:

```powershell
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
```

Or dot-source the project helper from the repo root:

```powershell
. .\scripts\dev-env.ps1
```

Per command:

```powershell
"Hello World" | Out-File -FilePath "file.txt" -Encoding utf8
```

If any file still ends up UTF-16, normalize before staging:

```powershell
python tools/fix_encoding.py
```



## Resume-linked search terms

Drop your résumé in 
esume/ (git-ignored). On **every scrape run**, AgentZero:

1. Reads the latest résumé in 
esume/
2. Uses the LLM to extract 
ecent_roles (newest job first)
3. Builds search_terms with **most recent job titles first**, then related keywords
4. Saves a local snapshot to 
esume/search_profile.json (also git-ignored) so you can inspect what was searched

Pass an LLM to JobSpySource(..., llm=provider) or run ingest_resume() — without an LLM, .env search terms are used as-is.

Example snapshot fields: search_terms, 
ecent_roles, locations, salary_min.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

Build progress is tracked in `PROGRESS.md` (checkboxes) and `WORKLOG.md` (append-only history).
