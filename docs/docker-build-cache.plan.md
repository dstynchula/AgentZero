# P30 — Docker incremental build cache

TDD Ralph plan: faster rebuilds when only `agentzero/` Python changes.

## Problem

- `COPY agentzero` before `pip install` invalidated pip + Playwright on every code edit.
- `PIP_NO_CACHE_DIR=1` disabled pip wheel cache.

## Approach

1. **Layer order:** `pyproject.toml` → stub `agentzero/__init__.py` → `pip install -e` → Playwright → `COPY agentzero`.
2. **BuildKit:** `# syntax=docker/dockerfile:1` + pip `RUN --mount=type=cache`.
3. **Dev override:** optional `docker-compose.override.yml` bind-mount for `agentzero/`.
4. **Build script / CI:** `DOCKER_BUILDKIT=1` (and `COMPOSE_DOCKER_CLI_BUILD=1` for compose).

## Tasks

- [x] P30a Dockerfile layer reorder + pip cache mount
- [x] P30b `docker_build.py` BuildKit env
- [x] P30c CI `DOCKER_BUILDKIT=1`
- [x] P30d `docker-compose.override.yml.example` + `.gitignore`
- [x] P30e Docs + tests + PROGRESS ledger

## Acceptance

- `pytest tests/test_dockerfile_cache.py -q`
- `ruff check agentzero tests scripts tools`
- Rebuild after editing only `agentzero/web/app.py`: pip + Playwright layers cache-hit (plain progress shows `CACHED`).
