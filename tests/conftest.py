"""Shared pytest fixtures for oldman_agent."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import duckdb
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> Path:
    """Fresh DuckDB file path per test (function scope)."""
    return tmp_path / "test.duckdb"


@pytest.fixture()
def tmp_db(tmp_db_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """Fresh DuckDB connection per test with migrations applied."""
    from app.storage.db import apply_migrations, get_conn

    conn = get_conn(str(tmp_db_path))
    apply_migrations(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest_asyncio.fixture()
async def async_client(tmp_db_path: Path) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient against the FastAPI app with a tmp DB."""
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
