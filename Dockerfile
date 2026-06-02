# syntax=docker/dockerfile:1
# agentzero-build-step: base
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# agentzero-build-step: apt
RUN echo "agentzero-build-step: apt" && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# agentzero-build-step: pip
# Stub package so pip resolves extras; real sources copied after pip + Playwright layers.
COPY pyproject.toml README.md ./
RUN mkdir -p agentzero && touch agentzero/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    echo "agentzero-build-step: pip" && pip install -e ".[scrape,llm,google,web]"

# agentzero-build-step: playwright
RUN echo "agentzero-build-step: playwright" && playwright install --with-deps chromium

# agentzero-build-step: copy
COPY agentzero ./agentzero
COPY scripts ./scripts
COPY docs ./docs

CMD ["python", "scripts/run_scrape.py", "--help"]
