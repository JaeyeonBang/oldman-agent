"""Phase 2.6 — RED tests: publish 후 background reflection 실행."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import duckdb
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.llm.base import LLMRequest, LLMResponse

# ── canned provider ──────────────────────────────────────────────────────────

_CANNED_JSON = (
    '{"summary": "테스트 반성", "descriptors": ["감시형"], "evidence_event_ids": []}'
)


class _CannedProvider:
    name = "canned"
    model = "canned-1"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text=_CANNED_JSON,
            model=self.model,
            tier=req.tier,
            input_tokens=100,
            output_tokens=20,
        )


class _RaisingProvider:
    name = "raising"
    model = "raising-1"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        raise RuntimeError("LLM 폭발")


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def app_with_canned_provider(
    tmp_db_path: Path,
) -> AsyncIterator[tuple[AsyncClient, _CannedProvider]]:
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app

    app = create_app()
    provider = _CannedProvider()
    app.state.reflection_provider = provider
    app.state.reflection_done = asyncio.Event()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, provider


@pytest_asyncio.fixture()
async def app_with_raising_provider(
    tmp_db_path: Path,
) -> AsyncIterator[AsyncClient]:
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app

    app = create_app()
    app.state.reflection_provider = _RaisingProvider()
    app.state.reflection_done = asyncio.Event()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _payload(i: int, observed: str | None = None) -> dict:
    p = {
        "source_agent": "agent_alice",
        "event_kind": "observation",
        "declared_source_type": "self",
        "payload": {"msg": f"msg_{i}", "i": i},
    }
    if observed is not None:
        p["observed_agent"] = observed
    return p


# ── tests ────────────────────────────────────────────────────────────────────

class TestPublishWithReflection:
    @pytest.mark.asyncio
    async def test_publish_below_threshold_no_reflection(
        self,
        app_with_canned_provider: tuple[AsyncClient, _CannedProvider],
        tmp_db_path: Path,
    ) -> None:
        client, provider = app_with_canned_provider
        # 3개만 publish
        for i in range(3):
            r = await client.post("/publish", json=_payload(i))
            assert r.status_code == 200

        # 백그라운드 작업이 완료될 짧은 시간 대기 (publish < threshold라 reflection 안 돔)
        await asyncio.sleep(0.2)

        # reflection 없음 확인 (다른 connection으로 검사)
        conn = duckdb.connect(str(tmp_db_path))
        try:
            row = conn.execute("SELECT COUNT(*) FROM reflections").fetchone()
            assert row is not None
            assert row[0] == 0
            assert provider.calls == 0
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_publish_triggers_reflection_at_threshold(
        self,
        app_with_canned_provider: tuple[AsyncClient, _CannedProvider],
        tmp_db_path: Path,
    ) -> None:
        client, _provider = app_with_canned_provider
        # 10개 publish → threshold trip
        for i in range(10):
            r = await client.post("/publish", json=_payload(i))
            assert r.status_code == 200

        # 백그라운드 reflection이 완료될 때까지 대기
        # 데모 스케일: 200ms 안에 끝나야 함 (mock provider라 빠름)
        for _ in range(50):  # 최대 5초
            await asyncio.sleep(0.1)
            conn = duckdb.connect(str(tmp_db_path))
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM reflections WHERE scope = 'agent'"
                ).fetchone()
                if row is not None and row[0] >= 1:
                    break
            finally:
                conn.close()

        conn = duckdb.connect(str(tmp_db_path))
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM reflections WHERE scope = 'agent' AND subject = 'agent_alice'"
            ).fetchone()
            assert row is not None
            assert row[0] >= 1, "10 publish 후 agent-scope reflection이 최소 1개 있어야 함"
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_reflection_failure_does_not_break_publish(
        self,
        app_with_raising_provider: AsyncClient,
    ) -> None:
        client = app_with_raising_provider
        # 10개 publish — LLM이 폭발해도 모두 200 반환해야 함
        for i in range(10):
            r = await client.post("/publish", json=_payload(i))
            assert r.status_code == 200, (
                f"publish #{i} 실패: {r.status_code} {r.text}"
            )

        await asyncio.sleep(0.3)
        # 추가 검증 불필요: publish 자체가 성공한 것이 acceptance

    @pytest.mark.asyncio
    async def test_publish_with_observed_agent_creates_pair_reflection(
        self,
        app_with_canned_provider: tuple[AsyncClient, _CannedProvider],
        tmp_db_path: Path,
    ) -> None:
        client, _ = app_with_canned_provider
        # 10개 publish — alice → bob 페어
        for i in range(10):
            r = await client.post("/publish", json=_payload(i, observed="agent_bob"))
            assert r.status_code == 200

        # background 완료 대기
        for _ in range(50):
            await asyncio.sleep(0.1)
            conn = duckdb.connect(str(tmp_db_path))
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM reflections WHERE scope = 'pair'"
                ).fetchone()
                if row is not None and row[0] >= 1:
                    break
            finally:
                conn.close()

        conn = duckdb.connect(str(tmp_db_path))
        try:
            row = conn.execute(
                "SELECT scope, subject FROM reflections WHERE scope = 'pair'"
            ).fetchone()
            assert row is not None
            assert row[0] == "pair"
            assert row[1] == "agent_alice:agent_bob"
        finally:
            conn.close()
