"""FastAPI factory for oldman_agent.

Run: ``uvicorn app.main:create_app --factory --port 8080 --workers 1``

``workers=1`` is mandatory — DuckDB is a single-writer engine and multi-process
contention against the same file leads to lock corruption (see README §M1).

v2 additions:
- mounts A2A JSON-RPC 2.0 surface at ``POST /``
- serves AgentCard at ``GET /.well-known/agent-card.json`` (SDK-standard path)
- OldmanAgentExecutor wired in app.state

Env loading: ``create_app()`` calls ``dotenv.load_dotenv()`` once on entry.
A ``.env`` at the project root (gitignored) is loaded with ``override=False`` —
explicit env vars set by tests / shell take precedence.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from a2a.client.card_resolver import parse_agent_card
from dotenv import load_dotenv
from fastapi import FastAPI

from app import __version__
from app.a2a.executor import OldmanAgentExecutor
from app.a2a.routes import build_a2a_routes
from app.api.agent_card import build_agent_card, card_to_well_known_dict
from app.api.agent_card import router as agent_card_router
from app.api.publish import router as publish_router
from app.api.query import router as query_router
from app.bootstrap import configure_providers
from app.config import get_settings
from app.storage.db import apply_migrations, get_conn

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _setup_app_logging() -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    level_name = os.environ.get("OLDMAN_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("app").setLevel(level)


def create_app() -> FastAPI:
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
        description="꼰대 정보통 — A2A v0.3 메타-기록자",
        lifespan=lifespan,
    )
    app.state.db = conn
    app.state.settings = settings

    # Wire LLM providers
    configure_providers(app)

    # Build agent card (env-driven)
    agent_card = build_agent_card()
    card_dict = card_to_well_known_dict(agent_card)
    # parse_agent_card mutates its input (compat shimming) — give it a copy
    # so the served well-known dict retains the v0.3 ``url`` field.
    import copy

    agent_card_proto = parse_agent_card(copy.deepcopy(card_dict))
    app.state.agent_card_dict = card_dict
    app.state.agent_card_proto = agent_card_proto

    # Wire A2A executor
    executor = OldmanAgentExecutor(
        conn=conn,
        settings=settings,
        narrative_provider=getattr(app.state, "narrative_provider", None),
        reflection_provider=getattr(app.state, "reflection_provider", None),
        judge_provider=getattr(app.state, "judge_provider", None),
    )
    app.state.a2a_executor = executor

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(publish_router)
    app.include_router(agent_card_router)
    app.include_router(query_router)

    # Mount A2A JSON-RPC + .well-known routes (Starlette routes directly on app.router)
    a2a_routes = build_a2a_routes(executor, agent_card_proto, card_dict)
    app.router.routes.extend(a2a_routes)

    return app
