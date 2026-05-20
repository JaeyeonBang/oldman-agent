"""FastAPI factory for oldman_agent M1.

Run: ``uvicorn app.main:create_app --factory --port 8080 --workers 1``

``workers=1`` is mandatory — DuckDB is a single-writer engine and multi-process
contention against the same file leads to lock corruption (see README §M1).

Env loading (v1.0.4): ``create_app()`` calls ``dotenv.load_dotenv()`` once on
entry. A ``.env`` at the project root (gitignored) is loaded with
``override=False`` — explicit env vars set by tests / shell take precedence.
See ``.env.example`` for the template.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app import __version__
from app.api.agent_card import router as agent_card_router
from app.api.publish import router as publish_router
from app.api.query import router as query_router
from app.bootstrap import configure_providers
from app.config import get_settings
from app.storage.db import apply_migrations, get_conn

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _setup_app_logging() -> None:
    """v1.0.6: app.* 네임스페이스 로거가 uvicorn stdout으로 흐르도록 한다.

    OLDMAN_LOG_LEVEL env로 레벨 조정 (기본 INFO). pytest는 이미 자체 caplog/
    logger config를 쓰므로 ``PYTEST_CURRENT_TEST`` env 존재 시 no-op.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    level_name = os.environ.get("OLDMAN_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    # 우리 코드의 _LOG.warning/info가 보이도록 root에 핸들러 부착.
    # uvicorn 기본 핸들러는 access log만 처리하고 app 로거는 propagate 안 됨.
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    root.setLevel(level)
    # app.* 로거도 명시적으로 레벨 지정 (root level이 더 높으면 무시되지 않도록).
    logging.getLogger("app").setLevel(level)


def create_app() -> FastAPI:
    # .env 자동 로드 — 파일 없으면 no-op. override=False라서 이미 설정된 환경변수
    # (pytest fixtures, shell export 등)가 우선. .env는 dev 보조용.
    load_dotenv(_ENV_FILE, override=False)
    _setup_app_logging()
    settings = get_settings()
    conn = get_conn(settings.db_path)
    apply_migrations(conn)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            conn.close()

    app = FastAPI(
        title="oldman_agent",
        version=__version__,
        description="꼰대 정보통 — A2A 메타-기록자 (M1 surface)",
        lifespan=lifespan,
    )
    app.state.db = conn
    app.state.settings = settings

    # Wire LLM providers — mock by default, AnthropicProvider if ANTHROPIC_API_KEY set.
    # Tests that need custom providers overwrite app.state.* after create_app() returns.
    configure_providers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(publish_router)
    app.include_router(agent_card_router)
    app.include_router(query_router)

    return app
