# agentzero-build-step: base
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# agentzero-build-step: apt
RUN echo "agentzero-build-step: apt" && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# agentzero-build-step: pip
COPY pyproject.toml README.md ./
COPY agentzero ./agentzero
RUN echo "agentzero-build-step: pip" && pip install -e ".[scrape,llm,google,web]"

# agentzero-build-step: playwright
RUN echo "agentzero-build-step: playwright" && playwright install --with-deps chromium

# agentzero-build-step: copy
COPY scripts ./scripts
COPY docs ./docs

CMD ["python", "scripts/run_scrape.py", "--help"]
