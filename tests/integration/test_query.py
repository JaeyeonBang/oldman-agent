"""Phase 3.5 — RED tests: POST /query endpoint."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.llm.base import LLMRequest, LLMResponse

# ── canned providers ──────────────────────────────────────────────────────────

class _CannedNarrativeProvider:
    """유효한 인용 마커를 포함한 텍스트를 반환하는 Provider."""
    name = "canned_narrative"
    model = "canned-1"

    def __init__(self, event_ids: list[str]) -> None:
        self.event_ids = event_ids

    async def complete(self, req: LLMRequest) -> LLMResponse:
        markers = " ".join(f"[↑e{eid[:8]}]" for eid in self.event_ids[:3])
        text = f"agent_alice가 여러 행동을 기록했습니다 {markers}."
        return LLMResponse(text=text, model=self.model, tier=req.tier)


class _AlwaysInvalidNarrativeProvider:
    """항상 존재하지 않는 마커를 반환해 validator를 실패시키는 Provider."""
    name = "always_invalid"
    model = "invalid-1"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="agent_alice가 뭔가를 했습니다 [↑eff000000].",
            model=self.model,
            tier=req.tier,
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _pub_payload(i: int, source_agent: str = "agent_alice") -> dict:
    return {
        "event_kind": "observation",
        "source_agent": source_agent,
        "declared_source_type": "self",
        "payload": {"msg": f"msg_{i}", "i": i},
    }


def _insert_reflection(conn: duckdb.DuckDBPyConnection) -> None:
    rid = str(uuid.uuid4())
    ts = datetime.now(UTC)
    conn.execute(
        "INSERT INTO reflections "
        "(reflection_id, ts, scope, subject, text, event_range_start, event_range_end, source_event_ids) "
        "VALUES (?, ?, 'agent', 'agent_alice', 'test', ?, ?, '[]')",
        [rid, ts, ts, ts],
    )


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def app_no_provider(tmp_db_path: Path) -> AsyncIterator[AsyncClient]:
    """narrative_provider 미설정 — 503 테스트용.

    bootstrap이 MockProvider를 주입하므로 명시적으로 제거해 503 경로를 테스트한다.
    """
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app
    app = create_app()
    # bootstrap이 주입한 mock을 제거 → /query가 503을 반환해야 함
    del app.state.narrative_provider
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture()
async def app_with_cold_start(tmp_db_path: Path) -> AsyncIterator[AsyncClient]:
    """빈 DB + canned provider — cold-start 테스트용."""
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app
    app = create_app()
    # provider는 있지만 DB가 비어있음 → cold start
    app.state.narrative_provider = _CannedNarrativeProvider([])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture()
async def seeded_app(
    tmp_db_path: Path,
) -> AsyncIterator[tuple[AsyncClient, list[str]]]:
    """5개 이벤트 + 1 reflection 시드 + canned provider."""
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app
    app = create_app()

    # 이벤트 직접 삽입 (publish 호출 없이 빠르게)
    conn = app.state.db
    event_ids: list[str] = []
    for i in range(5):
        eid = str(uuid.uuid4())
        ts = datetime.now(UTC)
        conn.execute(
            "INSERT INTO events "
            "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
            "VALUES (?, ?, 'observation', 'agent_alice', 'self', ?, ?)",
            [eid, ts, json.dumps({"i": i}), uuid.uuid4().hex],
        )
        event_ids.append(eid)
    _insert_reflection(conn)

    app.state.narrative_provider = _CannedNarrativeProvider(event_ids)
    # bootstrap이 MockProvider judge를 주입했으므로 grounded judge로 교체
    # (MockProvider는 "[mock]" → parse_error → is_grounded=False → fallback)
    app.state.judge_provider = _GroundedJudgeProvider()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, event_ids


@pytest_asyncio.fixture()
async def seeded_app_invalid_provider(
    tmp_db_path: Path,
) -> AsyncIterator[AsyncClient]:
    """이벤트 + reflection 시드 + always-invalid provider (fallback 강제)."""
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app
    app = create_app()

    conn = app.state.db
    for i in range(5):
        eid = str(uuid.uuid4())
        ts = datetime.now(UTC)
        conn.execute(
            "INSERT INTO events "
            "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
            "VALUES (?, ?, 'observation', 'agent_alice', 'self', ?, ?)",
            [eid, ts, json.dumps({"i": i}), uuid.uuid4().hex],
        )
    _insert_reflection(conn)

    app.state.narrative_provider = _AlwaysInvalidNarrativeProvider()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── tests ─────────────────────────────────────────────────────────────────────

class TestQueryEndpoint:
    @pytest.mark.asyncio
    async def test_query_cold_start_returns_fallback_message(
        self, app_with_cold_start: AsyncClient
    ) -> None:
        from app.state.cold_start import COLD_START_FALLBACK_MESSAGE
        r = await app_with_cold_start.post(
            "/query", json={"question": "agent_alice는 누구인가?"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["is_cold_start"] is True
        assert body["answer"] == COLD_START_FALLBACK_MESSAGE
        assert body["citations"] == []

    @pytest.mark.asyncio
    async def test_query_with_provider_unconfigured_returns_503(
        self, app_no_provider: AsyncClient
    ) -> None:
        r = await app_no_provider.post(
            "/query", json={"question": "agent_alice는 누구인가?"}
        )
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["status"] == "unavailable"
        assert detail["reason"] == "narrative_provider_unconfigured"

    @pytest.mark.asyncio
    async def test_query_with_evidence_returns_narrative_with_citations(
        self, seeded_app: tuple[AsyncClient, list[str]]
    ) -> None:
        client, event_ids = seeded_app
        r = await client.post(
            "/query",
            json={"question": "agent_alice가 최근 무엇을 했나요?", "subject_agent": "agent_alice"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["is_cold_start"] is False
        assert body["used_fallback"] is False
        assert len(body["answer"]) > 0
        assert len(body["citations"]) > 0
        # citations의 short_id가 실제 event_id 앞 8자리인지 확인
        returned_sids = {c["short_id"] for c in body["citations"]}
        expected_sids = {eid[:8] for eid in event_ids}
        assert returned_sids.issubset(expected_sids)

    @pytest.mark.asyncio
    async def test_query_subject_filter_narrows_evidence(
        self, seeded_app: tuple[AsyncClient, list[str]]
    ) -> None:
        client, _ = seeded_app
        # agent_bob은 이벤트 없음 → fallback 반환
        r = await client.post(
            "/query",
            json={"question": "agent_bob은?", "subject_agent": "agent_bob"},
        )
        assert r.status_code == 200
        body = r.json()
        # agent_bob 데이터 없으므로 fallback
        assert body["used_fallback"] is True

    @pytest.mark.asyncio
    async def test_query_validates_request_schema(
        self, seeded_app: tuple[AsyncClient, list[str]]
    ) -> None:
        client, _ = seeded_app
        # 빈 question → 422
        r = await client.post("/query", json={"question": ""})
        assert r.status_code == 422

        # extra field → 422
        r = await client.post(
            "/query", json={"question": "valid", "extra_field": "oops"}
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_query_when_validator_exhausts_retries_returns_fallback(
        self, seeded_app_invalid_provider: AsyncClient
    ) -> None:
        from app.state.cold_start import COLD_START_FALLBACK_MESSAGE
        r = await seeded_app_invalid_provider.post(
            "/query",
            json={"question": "agent_alice는?", "subject_agent": "agent_alice"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["used_fallback"] is True
        assert body["answer"] == COLD_START_FALLBACK_MESSAGE
        assert body["retries_used"] == 2


# ── Phase 4.4 — strict mode wiring tests ─────────────────────────────────────

class _GroundedJudgeProvider:
    """항상 is_grounded=True 반환하는 judge provider."""
    name = "grounded_judge"
    model = "gj-test-1"

    def __init__(self) -> None:
        self.calls: int = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text='{"is_grounded": true, "reason": "일치"}',
            model=self.model,
            tier=req.tier,
        )


@pytest_asyncio.fixture()
async def seeded_app_with_judge(
    tmp_db_path: Path,
) -> AsyncIterator[tuple[AsyncClient, list[str], _GroundedJudgeProvider]]:
    """judge_provider가 설정된 시드 앱 — strict mode 테스트용."""
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app
    app = create_app()

    conn = app.state.db
    event_ids: list[str] = []
    for i in range(5):
        eid = str(uuid.uuid4())
        ts = datetime.now(UTC)
        conn.execute(
            "INSERT INTO events "
            "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
            "VALUES (?, ?, 'observation', 'agent_alice', 'self', ?, ?)",
            [eid, ts, json.dumps({"i": i}), uuid.uuid4().hex],
        )
        event_ids.append(eid)
    _insert_reflection(conn)

    narrative_provider = _CannedNarrativeProvider(event_ids)
    judge_provider = _GroundedJudgeProvider()

    app.state.narrative_provider = narrative_provider
    app.state.judge_provider = judge_provider

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, event_ids, judge_provider


@pytest_asyncio.fixture()
async def seeded_app_no_judge(
    tmp_db_path: Path,
) -> AsyncIterator[AsyncClient]:
    """judge_provider 없는 시드 앱 — fallback-to-existence 테스트용."""
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app
    app = create_app()

    conn = app.state.db
    event_ids: list[str] = []
    for i in range(5):
        eid = str(uuid.uuid4())
        ts = datetime.now(UTC)
        conn.execute(
            "INSERT INTO events "
            "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
            "VALUES (?, ?, 'observation', 'agent_alice', 'self', ?, ?)",
            [eid, ts, json.dumps({"i": i}), uuid.uuid4().hex],
        )
        event_ids.append(eid)
    _insert_reflection(conn)

    app.state.narrative_provider = _CannedNarrativeProvider(event_ids)
    # judge_provider 미설정 테스트 — bootstrap이 주입한 mock을 모두 제거.
    # query.py: judge_provider → reflection_provider 순으로 fallback하므로
    # 둘 다 제거해야 "미설정" 경로가 동작한다.
    del app.state.judge_provider
    del app.state.reflection_provider

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestQueryStrictMode:
    @pytest.mark.asyncio
    async def test_query_strict_mode_default_uses_judge(
        self, seeded_app_with_judge: tuple[AsyncClient, list[str], _GroundedJudgeProvider]
    ) -> None:
        """strict_mode=true (기본값) 으로 요청 시 judge provider가 호출된다."""
        client, _event_ids, judge_provider = seeded_app_with_judge

        r = await client.post(
            "/query",
            json={
                "question": "agent_alice가 최근 무엇을 했나요?",
                "subject_agent": "agent_alice",
                "strict_mode": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["used_fallback"] is False
        # judge provider가 최소 1회 호출되어야 함
        assert judge_provider.calls >= 1

    @pytest.mark.asyncio
    async def test_query_strict_false_uses_existence_only(
        self, seeded_app_with_judge: tuple[AsyncClient, list[str], _GroundedJudgeProvider]
    ) -> None:
        """strict_mode=false 요청 시 judge 호출 없이 존재 검증만 수행한다."""
        client, _event_ids, judge_provider = seeded_app_with_judge
        calls_before = judge_provider.calls

        r = await client.post(
            "/query",
            json={
                "question": "agent_alice가 최근 무엇을 했나요?",
                "subject_agent": "agent_alice",
                "strict_mode": False,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["used_fallback"] is False
        # judge provider 호출 없어야 함
        assert judge_provider.calls == calls_before

    @pytest.mark.asyncio
    async def test_query_strict_no_judge_provider_falls_back_to_existence_with_warning_log(
        self, seeded_app_no_judge: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """judge_provider 미설정 + strict_mode=true → existence-only로 downgrade, 200 반환."""
        import logging
        with caplog.at_level(logging.WARNING):
            r = await seeded_app_no_judge.post(
                "/query",
                json={
                    "question": "agent_alice가 최근 무엇을 했나요?",
                    "subject_agent": "agent_alice",
                    "strict_mode": True,
                },
            )

        assert r.status_code == 200
        body = r.json()
        # downgrade 후 존재 검증 통과 → 정상 응답
        assert body["used_fallback"] is False
        # 경고 로그가 기록되어야 함
        assert any("judge" in rec.message.lower() or "strict" in rec.message.lower()
                   for rec in caplog.records)
