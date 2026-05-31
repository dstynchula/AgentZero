# Public release checklist

Use this before pushing AgentZero to a public GitHub repository.

## 1) Security + privacy gate

- [ ] Rotate API keys and OAuth tokens before first public push
- [ ] Verify `.env`, `token.json`, `client_secret.json`, browser profiles, and local DB files are not tracked
- [ ] Confirm no personal resume or cover-letter content is tracked
- [ ] Run: `python tools/fix_encoding.py`
- [ ] Run: `git status` and confirm only intentional files are present

## 2) Quality gate

- [ ] Run: `ruff check agentzero tests scripts tools`
- [ ] Run: `pytest -q`
- [ ] Verify CI workflow exists and is green: `.github/workflows/ci.yml`
- [ ] Add README CI badge (already wired to `.github/workflows/ci.yml`)
- [ ] Enable branch protection on `main`:
  - Require pull request before merging
  - Require status checks to pass before merging (`test`)
  - Dismiss stale approvals when new commits are pushed
- [ ] Confirm docs and code agree on current scope (no stale MVP-only claims)

## 3) Public signal gate (portfolio quality)

- [ ] README has quick start, architecture, tradeoffs, and security links
- [ ] SECURITY.md explains trust boundary and known limitations
- [ ] BUILD_STORY.md explains how agent pairing was used with quality controls
- [ ] PROGRESS.md and WORKLOG.md are coherent and up to date

## 4) Include vs exclude (recommended)

### Include

- Source code (`agentzero/`, `scripts/`, `tests/`)
- Core docs (`README.md`, `docs/*.md`, `PROGRESS.md`, `WORKLOG.md`)
- CI + repo policy (`.github/`, `.gitignore`, `.gitattributes`, `LICENSE`)
- Cursor collaboration artifacts you want to showcase (`.cursor/`, `AGENTS.md`)

### Exclude

- Local secrets and OAuth tokens (`.env`, `token.json`, `client_secret.json`)
- Local runtime state (`data/*.db`, browser profiles, storage state, logs)
- Local outputs (`output/`, temporary debug dumps)
- Any personally identifying resume artifacts outside placeholders (`resume/.gitkeep`)

## 5) Optional launch polish

- [ ] Tag first public baseline (example: `v0.1.0-public`)
- [ ] Add release notes summarizing scope and known limitations
- [ ] Pin one issue called "Roadmap" so reviewers see intentional next steps
