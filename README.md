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

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

Build progress is tracked in `PROGRESS.md` (checkboxes) and `WORKLOG.md` (append-only history).
