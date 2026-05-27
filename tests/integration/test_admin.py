"""``GET /admin/memory`` smoke + token guard."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture()
async def admin_client(tmp_db_path: Path) -> AsyncIterator[AsyncClient]:
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    os.environ.pop("OLDMAN_ADMIN_TOKEN", None)
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.state.db.close()


@pytest.mark.asyncio
async def test_admin_memory_empty_db(admin_client: AsyncClient) -> None:
    r = await admin_client.get("/admin/memory")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"] == {
        "events": 0,
        "entities_semantic": 0,
        "entities_episodic": 0,
        "reflections": 0,
    }
    assert body["agents"] == []
    assert body["recent_events"] == []
    assert body["recent_reflections"] == []
    assert body["traits_compiled"] == {}


@pytest.mark.asyncio
async def test_admin_memory_after_publish(admin_client: AsyncClient) -> None:
    from tests._a2a_helpers import publish_event

    status, ack = await publish_event(
        admin_client,
        event_kind="chat",
        source_agent="agent_alice",
        observed_agent="agent_bob",
        declared_source_type="third_party",
        payload={"text": "hi from admin smoke"},
    )
    assert status == 200
    assert ack.get("status") == "stored"

    r = await admin_client.get("/admin/memory")
    body = r.json()
    assert body["counts"]["events"] == 1
    assert body["counts"]["entities_episodic"] == 1
    assert body["counts"]["entities_semantic"] == 2  # alice + bob
    assert set(body["agents"]) == {"agent_alice", "agent_bob"}
    assert len(body["recent_events"]) == 1
    ev = body["recent_events"][0]
    assert ev["kind"] == "chat"
    assert ev["source_agent"] == "agent_alice"
    assert ev["payload"]["text"] == "hi from admin smoke"


@pytest.mark.asyncio
async def test_admin_memory_token_required_when_set(
    tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OLDMAN_ADMIN_TOKEN", "secret-" + uuid.uuid4().hex[:8])
    monkeypatch.setenv("OLDMAN_DB_PATH", str(tmp_db_path))
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/admin/memory")
        assert r.status_code == 401
        r = await c.get("/admin/memory?token=wrong")
        assert r.status_code == 401
        r = await c.get(
            f"/admin/memory?token={os.environ['OLDMAN_ADMIN_TOKEN']}"
        )
        assert r.status_code == 200
        r = await c.get(
            "/admin/memory",
            headers={"X-Admin-Token": os.environ["OLDMAN_ADMIN_TOKEN"]},
        )
        assert r.status_code == 200
    app.state.db.close()
