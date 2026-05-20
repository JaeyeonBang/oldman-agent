# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# uv: fast Python package installer
RUN pip install --no-cache-dir uv==0.5.4

# Copy only dependency manifests first (layer cache)
COPY pyproject.toml README.md ./

# Create venv and install runtime deps only (no dev extras)
RUN uv venv .venv && \
    uv pip install --no-cache --python .venv/bin/python \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "duckdb>=1.1.0" \
        "pydantic>=2.5" \
        "httpx>=0.27.0" \
        "pyyaml>=6.0"

# Copy application source
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY config/ ./config/

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy venv and app from builder (no dev deps, no tests, no source cache)
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY --from=builder /app/prompts /app/prompts
COPY --from=builder /app/config /app/config

# DuckDB 파일 경로 — docker-compose에서 named volume으로 마운트
ENV OLDMAN_DB_PATH=/data/oldman.duckdb

# workers=1 필수: DuckDB는 단일 파일 단일 writer
EXPOSE 8080

CMD ["/app/.venv/bin/uvicorn", "app.main:create_app", \
     "--factory", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1"]
