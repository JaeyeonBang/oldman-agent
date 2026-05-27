# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# uv: fast Python package installer
RUN pip install --no-cache-dir uv==0.5.4

# Copy only dependency manifests first (layer cache)
COPY pyproject.toml README.md ./

# Create venv + install runtime deps (v2 fix: hardcoded list was stale).
# Includes a2a-sdk + python-dotenv + sse-starlette added after v1.0.0.
RUN uv venv .venv && \
    uv pip install --no-cache --python .venv/bin/python \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "duckdb>=1.1.0" \
        "pydantic>=2.5" \
        "httpx>=0.27.0" \
        "pyyaml>=6.0" \
        "a2a-sdk[http-server]>=1.0,<2.0" \
        "python-dotenv>=1.0" \
        "sse-starlette>=3.0"

# Copy application source
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY config/ ./config/

# v2: 컨테이너 이미지는 openrouter config를 default로 사용 (production-like).
# 로컬 pytest는 소스 config/llm.yaml (mock)을 그대로 쓰고, docker-compose는
# bind-mount로 동일 파일을 override한다. fly 같은 단순 배포는 이미지 내용만 사용
# 하므로 build 시 덮어써야 한다.
RUN cp /app/config/llm.docker.yaml /app/config/llm.yaml

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# v2.3: HF Spaces 호환 — non-root user 1000 필수.
# docker-compose / Fly가 /data 영속 볼륨을 쓸 땐 별도 chown 필요 (deferred).
RUN useradd -m -u 1000 user

# Copy venv and app from builder (chown to non-root user)
COPY --from=builder --chown=user:user /app/.venv /app/.venv
COPY --from=builder --chown=user:user /app/app /app/app
COPY --from=builder --chown=user:user /app/prompts /app/prompts
COPY --from=builder --chown=user:user /app/config /app/config

# DuckDB 파일 경로 — default: /tmp (HF Spaces ephemeral, user 1000 항상 쓰기 가능).
# 영속 마운트 환경 (docker-compose /data, Fly /data)은 OLDMAN_DB_PATH env로 override.
ENV OLDMAN_DB_PATH=/tmp/oldman.duckdb

# HF Spaces, docker-compose, Fly 모두 동일 포트 8080 사용.
# (HF는 README.md frontmatter의 app_port:8080을 읽음)
EXPOSE 8080

USER user

# workers=1 필수: DuckDB는 단일 파일 단일 writer
CMD ["/app/.venv/bin/uvicorn", "app.main:create_app", \
     "--factory", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1"]
