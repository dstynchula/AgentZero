# Contributing to AgentZero

Thanks for your interest in contributing! AgentZero is a local, resume-driven
job-search agent and an open example of agentic co-programming. Contributions of
all sizes are welcome.

By participating, you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Getting started

```bash
python -m venv .venv
# Windows:  . .venv\Scripts\Activate.ps1
# macOS/Linux:  source .venv/bin/activate
pip install -e ".[dev,scrape,llm,google,mcp]"
```

See [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) for the full setup
(Chrome for CAPTCHA, the daily loop, etc.).

## Development workflow

This project follows a TDD-first, small-step loop. Before opening a PR, make
sure all of the local gates pass:

```bash
ruff check agentzero tests scripts tools   # lint + import order
pytest -q                                  # full test suite
python tools/encoding_check.py             # UTF-8 / no UTF-16 text files
```

These are the same checks CI enforces (`.github/workflows/ci.yml`). Ruff is
pinned (`ruff==0.15.15`) so local and CI results match.

Guidelines:

- **Write tests first** where practical; cover parser drift, policy, and safety
  paths.
- **Keep PRs small and focused.** Large changes are easier to review when split.
- **Don't commit secrets or personal data** — resumes, tokens, `client_secret.json`,
  local databases, and browser profiles are all covered by `.gitignore`. Double
  check `git status` before committing.
- **Update docs** (`README.md` / `docs/`) when you change behavior or setup.

## Commit and PR conventions

- Use clear, imperative commit subjects with a conventional prefix where it
  fits: `fix:`, `feat:`, `chore:`, `docs:`, `test:`, `refactor:`.
- Explain the "why" in the body, not just the "what".
- Open PRs against `main`. CI must be green and the
  [pull request template](.github/pull_request_template.md) filled out.
- `main` is protected: changes land via reviewed pull requests.

## Reporting bugs and requesting features

Open a GitHub issue with:

- What you expected to happen and what actually happened
- Steps to reproduce (commands, config, board involved)
- Relevant logs or tracebacks (with secrets/personal data redacted)

## Security

Please do **not** open public issues for security problems. See
[docs/SECURITY.md](docs/SECURITY.md) for how to report vulnerabilities privately.
