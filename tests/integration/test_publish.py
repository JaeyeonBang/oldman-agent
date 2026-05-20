"""Phase 1.4 RED: /publish integration (full pipeline + T2/T4 regressions)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_publish_valid_event_returns_200(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/publish",
        json={
            "event_kind": "chat",
            "source_agent": "agent_alice",
            "observed_agent": "agent_bob",
            "declared_source_type": "third_party",
            "payload": {"text": "안녕 친구"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "stored"
    assert body["event_id"]


@pytest.mark.asyncio
async def test_publish_blocklisted_kind_returns_422(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/publish",
        json={
            "event_kind": "heartbeat",
            "source_agent": "a",
            "declared_source_type": "self",
            "payload": {"v": "1"},
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason"] == "blocklisted_kind"


@pytest.mark.asyncio
async def test_publish_extra_field_returns_422(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/publish",
        json={
            "event_kind": "chat",
            "source_agent": "a",
            "declared_source_type": "self",
            "payload": {"v": "1"},
            "stray": "nope",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_publish_invalid_source_type_returns_422(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/publish",
        json={
            "event_kind": "chat",
            "source_agent": "a",
            "declared_source_type": "bogus",
            "payload": {"v": "1"},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_publish_serial_duplicate_returns_409(async_client: AsyncClient) -> None:
    """Serial repost — Jaccard scan (step 3 of plan §0 algorithm) fires before
    INSERT because identical tokens score 1.0 ≥ 0.9. Concurrent same-hash hits
    exact_hash via UNIQUE constraint (see T4 regression test below)."""
    payload = {
        "event_kind": "chat",
        "source_agent": "a",
        "declared_source_type": "self",
        "payload": {"v": "identical"},
    }
    r1 = await async_client.post("/publish", json=payload)
    assert r1.status_code == 200
    r2 = await async_client.post("/publish", json=payload)
    assert r2.status_code == 409
    assert r2.json()["detail"]["reason"] in {"jaccard_near_duplicate", "exact_hash"}


@pytest.mark.asyncio
async def test_publish_near_duplicate_returns_409(async_client: AsyncClient) -> None:
    base_tokens = " ".join(f"tok{i}" for i in range(20))
    r1 = await async_client.post(
        "/publish",
        json={
            "event_kind": "chat",
            "source_agent": "alice",
            "declared_source_type": "self",
            "payload": {"text": base_tokens},
        },
    )
    assert r1.status_code == 200
    near = " ".join(f"tok{i}" for i in range(19))
    r2 = await async_client.post(
        "/publish",
        json={
            "event_kind": "chat",
            "source_agent": "alice",
            "declared_source_type": "self",
            "payload": {"text": near},
        },
    )
    assert r2.status_code == 409
    assert r2.json()["detail"]["reason"] == "jaccard_near_duplicate"


@pytest.mark.asyncio
async def test_publish_observed_agent_touches_both_semantics(tmp_db_path: Path) -> None:
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/publish",
            json={
                "event_kind": "chat",
                "source_agent": "alice",
                "observed_agent": "bob",
                "declared_source_type": "third_party",
                "payload": {"text": "hi"},
            },
        )
        assert resp.status_code == 200
        conn = app.state.db
        agents = {
            r[0]
            for r in conn.execute(
                "SELECT agent_id FROM entities_semantic ORDER BY agent_id"
            ).fetchall()
        }
        assert agents == {"alice", "bob"}
        ep = conn.execute("SELECT count(*) FROM entities_episodic").fetchone()
        assert ep is not None and ep[0] == 1
        ev = conn.execute("SELECT count(*) FROM events").fetchone()
        assert ev is not None and ev[0] == 1


# T4 regression
@pytest.mark.asyncio
async def test_publish_concurrent_same_hash_only_one_succeeds(tmp_db_path: Path) -> None:
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = {
            "event_kind": "chat",
            "source_agent": "alice",
            "declared_source_type": "self",
            "payload": {"text": "race-me"},
        }
        results = await asyncio.gather(
            client.post("/publish", json=body),
            client.post("/publish", json=body),
        )
        codes = sorted(r.status_code for r in results)
        assert codes == [200, 409], f"expected one 200 + one 409, got {codes}"
        conn = app.state.db
        row = conn.execute("SELECT count(*) FROM events").fetchone()
        assert row is not None and row[0] == 1


# T2 regression
@pytest.mark.asyncio
async def test_publish_partial_tx_failure_rolls_back_events(
    tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.api import publish as publish_mod
    from app.main import create_app

    def boom(*args: object, **kwargs: object) -> str:
        raise RuntimeError("simulated L1 failure")

    monkeypatch.setattr(publish_mod.ent_store, "append_episodic", boom)

    app = create_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/publish",
            json={
                "event_kind": "chat",
                "source_agent": "alice",
                "declared_source_type": "self",
                "payload": {"text": "will-fail"},
            },
        )
        assert resp.status_code == 500
        conn = app.state.db
        row = conn.execute("SELECT count(*) FROM events").fetchone()
        assert row is not None and row[0] == 0
