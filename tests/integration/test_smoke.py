"""Phase 1.8/2.8/3.6 E2E smoke — happy path + M2 reflection cycle + M3 query."""

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


@pytest.mark.asyncio
async def test_smoke_full_publish_cycle(async_client: AsyncClient) -> None:
    h = await async_client.get("/health")
    assert h.status_code == 200 and h.json() == {"status": "ok"}

    c = await async_client.get("/agent-card")
    assert c.status_code == 200
    card = c.json()
    assert card["name"] == "oldman_agent"
    # v1.0.1: capabilities.publish removed; publish capability expressed via skill tag
    assert any("publish" in s.get("tags", []) for s in card["skills"])
    assert card["x-oldman"]["persona"] == "꼰대 정보통"

    from tests._a2a_helpers import publish_event

    _, ack1 = await publish_event(
        async_client,
        event_kind="chat",
        source_agent="agent_alice",
        observed_agent="agent_bob",
        declared_source_type="third_party",
        payload={"text": "smoke-test 한 번 가자"},
    )
    assert ack1.get("status") == "stored", ack1

    _, ack2 = await publish_event(
        async_client,
        event_kind="chat",
        source_agent="agent_alice",
        observed_agent="agent_bob",
        declared_source_type="third_party",
        payload={"text": "smoke-test 한 번 가자"},
    )
    assert ack2.get("status") == "deduplicated", ack2
    assert ack2.get("reason") in {"jaccard_near_duplicate", "exact_hash"}

    _, ack3 = await publish_event(
        async_client,
        event_kind="heartbeat",
        source_agent="a",
        declared_source_type="self",
        payload={"v": "1"},
    )
    assert ack3.get("status") == "blocked", ack3
    assert ack3.get("reason") == "blocklisted_kind"


# ── M2 smoke: 10-publish loop triggers reflection ──────────────────────────────

_M2_CANNED_JSON = (
    '{"summary": "smoke 반성", "descriptors": ["감시형"], "evidence_event_ids": []}'
)


class _SmokeCannedProvider:
    name = "smoke_canned"
    model = "smoke-1"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=_M2_CANNED_JSON,
            model=self.model,
            tier=req.tier,
            input_tokens=100,
            output_tokens=20,
        )


@pytest_asyncio.fixture()
async def m2_smoke_client(tmp_db_path: Path) -> AsyncIterator[tuple[AsyncClient, Path]]:
    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app

    app = create_app()
    canned = _SmokeCannedProvider()
    app.state.reflection_provider = canned
    # v2.1: executor caches providers at construction time → override here too
    app.state.a2a_executor.reflection_provider = canned
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, tmp_db_path


@pytest.mark.asyncio
async def test_m2_smoke_10_publish_triggers_reflection(
    m2_smoke_client: tuple[AsyncClient, Path],
) -> None:
    """M2 acceptance: 10 publish → ≥1 reflection row appears, traits_json populated."""
    from tests._a2a_helpers import publish_event

    client, db_path = m2_smoke_client

    for i in range(10):
        _, ack = await publish_event(
            client,
            event_kind="observation",
            source_agent="agent_alice",
            declared_source_type="self",
            payload={"i": i, "msg": f"smoke_msg_{i}"},
        )
        assert ack.get("status") == "stored", ack

    # background reflection 완료 대기
    for _ in range(50):
        await asyncio.sleep(0.1)
        conn = duckdb.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM reflections WHERE scope = 'agent'"
            ).fetchone()
            if row is not None and row[0] >= 1:
                break
        finally:
            conn.close()

    conn = duckdb.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM reflections WHERE scope = 'agent' AND subject = 'agent_alice'"
        ).fetchone()
        assert row is not None
        assert row[0] >= 1, "10 publish 후 agent-scope reflection이 최소 1개 있어야 함"

        # traits_json이 비어 있지 않은지 확인
        traits_row = conn.execute(
            "SELECT traits_json FROM entities_semantic WHERE agent_id = 'agent_alice'"
        ).fetchone()
        assert traits_row is not None
        # traits_json은 dict 형태로 summary/descriptors 포함
        import json
        loaded = json.loads(traits_row[0]) if isinstance(traits_row[0], str) else traits_row[0]
        assert loaded.get("summary") == "smoke 반성"
        assert "감시형" in loaded.get("descriptors", [])
    finally:
        conn.close()


# ── M3 smoke: /query returns cited narrative ───────────────────────────────────

class _M3GroundedJudgeProvider:
    """M3/M4 smoke용: 항상 is_grounded=True 반환해 citation 검증 통과."""

    name = "m3_smoke_grounded_judge"
    model = "grounded-judge-smoke-1"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text='{"is_grounded": true, "reason": "smoke test always grounded"}',
            model=self.model,
            tier=req.tier,
        )


class _M3CannedNarrativeProvider:
    """M3 smoke용: event_ids를 받아 유효한 인용 마커 포함 텍스트를 반환."""

    name = "m3_smoke_canned"
    model = "m3-smoke-1"

    def __init__(self, event_ids: list[str]) -> None:
        self.event_ids = event_ids

    async def complete(self, req: LLMRequest) -> LLMResponse:
        markers = " ".join(f"[↑e{eid[:8]}]" for eid in self.event_ids[:3])
        text = f"agent_alice가 10번의 이벤트를 기록했습니다 {markers}."
        return LLMResponse(text=text, model=self.model, tier=req.tier)


@pytest_asyncio.fixture()
async def m3_smoke_client(
    tmp_db_path: Path,
) -> AsyncIterator[tuple[AsyncClient, list[str]]]:
    """10개 이벤트 + 1 reflection 시드 + M3 canned narrative provider."""
    import json as _json
    import uuid as _uuid
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app

    app = create_app()
    conn = app.state.db

    # 10개 이벤트 직접 삽입
    event_ids: list[str] = []
    for i in range(10):
        eid = str(_uuid.uuid4())
        ts = _datetime.now(_UTC)
        conn.execute(
            "INSERT INTO events "
            "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
            "VALUES (?, ?, 'observation', 'agent_alice', 'self', ?, ?)",
            [eid, ts, _json.dumps({"i": i, "msg": f"smoke_m3_{i}"}), _uuid.uuid4().hex],
        )
        event_ids.append(eid)

    # 1개 reflection 삽입 (cold-start 통과용)
    rid = str(_uuid.uuid4())
    ts = _datetime.now(_UTC)
    conn.execute(
        "INSERT INTO reflections "
        "(reflection_id, ts, scope, subject, text, event_range_start, event_range_end, source_event_ids) "
        "VALUES (?, ?, 'agent', 'agent_alice', 'M3 smoke reflection', ?, ?, '[]')",
        [rid, ts, ts, ts],
    )

    narrative = _M3CannedNarrativeProvider(event_ids)
    judge = _M3GroundedJudgeProvider()
    app.state.narrative_provider = narrative
    app.state.judge_provider = judge
    # v2.1: executor caches providers; override executor refs too
    app.state.a2a_executor.narrative_provider = narrative
    app.state.a2a_executor.judge_provider = judge

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, event_ids


@pytest.mark.asyncio
async def test_m3_smoke_query_returns_cited_narrative(
    m3_smoke_client: tuple[AsyncClient, list[str]],
) -> None:
    """M3 acceptance: /query → 200, answer non-empty, citations exist, all short_ids in DB."""
    from tests._a2a_helpers import run_query

    client, event_ids = m3_smoke_client

    status, body = await run_query(
        client,
        question="agent_alice가 최근 무엇을 했나요?",
        subject_agent="agent_alice",
        max_citations=10,
    )
    assert status == 200, body

    assert body["is_cold_start"] is False
    assert body["used_fallback"] is False
    assert len(body["answer"]) > 0

    citations = body["citations"]
    assert len(citations) > 0, "citations이 비어 있으면 안 됩니다"

    # 모든 citation short_id가 실제 DB event_id 앞 8자리인지 확인
    valid_short_ids = {eid[:8] for eid in event_ids}
    for citation in citations:
        assert citation["short_id"] in valid_short_ids, (
            f"citation short_id {citation['short_id']} 가 DB event_ids에 없습니다"
        )


# ── M4 smoke: strict validator catches hallucination ─────────────────────────


class _M4FabricatedNarrativeProvider:
    """항상 FABRICATED 주장을 포함한 내러티브를 반환 — strict mode가 잡아야 한다."""

    name = "m4_fabricated"
    model = "m4-fab-1"

    def __init__(self, event_ids: list[str]) -> None:
        self.event_ids = event_ids

    async def complete(self, req: LLMRequest) -> LLMResponse:
        # 유효한 short_id를 사용하지만 주장은 FABRICATED_ 키워드 포함
        sid = self.event_ids[0][:8]
        text = (
            f"FABRICATED_agent_zara가 이 이벤트를 수행했습니다 [↑e{sid}]. "
            "실제 에이전트와 다른 주장."
        )
        return LLMResponse(text=text, model=self.model, tier=req.tier)


class _M4GroundedJudgeProvider:
    """FABRICATED_ 키워드 감지 시 is_grounded=False 반환하는 mock judge."""

    name = "m4_mock_judge"
    model = "m4-judge-1"

    def __init__(self) -> None:
        self.calls: int = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        is_grounded = "FABRICATED_" not in req.prompt
        verdict = "true" if is_grounded else "false"
        return LLMResponse(
            text=f'{{"is_grounded": {verdict}, "reason": "smoke test"}}',
            model=self.model,
            tier=req.tier,
        )


@pytest_asyncio.fixture()
async def m4_smoke_client(
    tmp_db_path: Path,
) -> AsyncIterator[tuple[AsyncClient, list[str], _M4GroundedJudgeProvider]]:
    """M4 smoke용: fabricated narrative + mock judge."""
    import json as _json
    import uuid as _uuid
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
    from app.main import create_app

    app = create_app()
    conn = app.state.db

    event_ids: list[str] = []
    for i in range(3):
        eid = str(_uuid.uuid4())
        ts = _datetime.now(_UTC)
        conn.execute(
            "INSERT INTO events "
            "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
            "VALUES (?, ?, 'observation', 'agent_alice', 'self', ?, ?)",
            [eid, ts, _json.dumps({"i": i, "agent": "agent_alice"}), _uuid.uuid4().hex],
        )
        event_ids.append(eid)

    rid = str(_uuid.uuid4())
    ts = _datetime.now(_UTC)
    conn.execute(
        "INSERT INTO reflections "
        "(reflection_id, ts, scope, subject, text, event_range_start, event_range_end, source_event_ids) "
        "VALUES (?, ?, 'agent', 'agent_alice', 'M4 smoke reflection', ?, ?, '[]')",
        [rid, ts, ts, ts],
    )

    judge = _M4GroundedJudgeProvider()
    narrative = _M4FabricatedNarrativeProvider(event_ids)
    app.state.narrative_provider = narrative
    app.state.judge_provider = judge
    # v2.1: executor caches providers; override executor refs too
    app.state.a2a_executor.narrative_provider = narrative
    app.state.a2a_executor.judge_provider = judge

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, event_ids, judge


@pytest.mark.asyncio
async def test_m4_smoke_strict_validator_catches_hallucination(
    m4_smoke_client: tuple[AsyncClient, list[str], _M4GroundedJudgeProvider],
) -> None:
    """M4 acceptance: strict validator가 existence 통과했지만 날조된 주장을 잡아 fallback."""
    from app.state.cold_start import COLD_START_FALLBACK_MESSAGE
    from tests._a2a_helpers import run_query

    client, _event_ids, judge = m4_smoke_client

    # strict_mode=True(기본) — fabricated narrative → judge가 잡음 → 재시도 → fallback
    status, body = await run_query(
        client,
        question="agent_alice가 최근 무엇을 했나요?",
        subject_agent="agent_alice",
        strict_mode=True,
    )
    assert status == 200, body

    assert body["used_fallback"] is True, (
        "fabricated 주장은 strict validator에 의해 잡혀 fallback이어야 합니다"
    )
    assert body["answer"] == COLD_START_FALLBACK_MESSAGE
    assert judge.calls >= 1, "judge provider가 호출되어야 합니다"

    status2, body2 = await run_query(
        client,
        question="agent_alice가 최근 무엇을 했나요?",
        subject_agent="agent_alice",
        strict_mode=False,
    )
    assert status2 == 200, body2
    assert body2["used_fallback"] is False, (
        "existence-only 모드에서는 short_id가 유효하므로 통과해야 합니다"
    )


# ── M5 smoke: bootstrap wires mock providers ──────────────────────────────────

@pytest.mark.asyncio
async def test_m5_smoke_bootstrap_wires_mock_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M5 acceptance: create_app() 호출 시 bootstrap이 mock provider 세 개를 주입한다.

    ANTHROPIC_API_KEY 없는 환경에서 세 provider 모두 non-None이고 MockProvider여야 한다.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLDMAN_DB_PATH", str(tmp_path / "m5_smoke.duckdb"))

    from app.llm.providers.mock import MockProvider
    from app.main import create_app

    app = create_app()

    reflection = getattr(app.state, "reflection_provider", None)
    judge = getattr(app.state, "judge_provider", None)
    narrative = getattr(app.state, "narrative_provider", None)

    assert reflection is not None, "reflection_provider should be set by bootstrap"
    assert judge is not None, "judge_provider should be set by bootstrap"
    assert narrative is not None, "narrative_provider should be set by bootstrap"

    assert isinstance(reflection, MockProvider), f"expected MockProvider, got {type(reflection)}"
    assert isinstance(judge, MockProvider), f"expected MockProvider, got {type(judge)}"
    assert isinstance(narrative, MockProvider), f"expected MockProvider, got {type(narrative)}"


# ── Phase 7.2: full-pipeline smoke with smart mock (no API keys) ──────────────

@pytest.mark.asyncio
async def test_full_pipeline_with_smart_mock_no_keys(
    tmp_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 7.2 acceptance: 10 publishes → reflection lands → /query returns citations.

    Uses smart MockProvider (no API keys needed).
    Closes the "is_cold_start=true after 10 publishes in dev mode" gap.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OLDMAN_DB_PATH", str(tmp_db_path))

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)

    from tests._a2a_helpers import publish_event, run_query

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: publish 10 events from agent_alice
        for i in range(10):
            _, ack = await publish_event(
                client,
                event_kind="observation",
                source_agent="agent_alice",
                declared_source_type="self",
                payload={"i": i, "msg": f"smart_mock_smoke_{i}"},
            )
            assert ack.get("status") == "stored", ack

        # Step 2: poll up to 5s for reflection to land
        # (BackgroundTasks runs scheduler; smart mock JSON parses → row lands)
        reflection_found = False
        for _ in range(50):
            await asyncio.sleep(0.1)
            conn = duckdb.connect(str(tmp_db_path))
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM reflections WHERE scope = 'agent'"
                ).fetchone()
                if row is not None and row[0] >= 1:
                    reflection_found = True
                    break
            finally:
                conn.close()

        assert reflection_found, (
            "10 publish 후 5초 이내에 reflection이 landing되어야 합니다 (smart mock 확인)"
        )

        # Step 3: /query — smart mock narrative provider returns citations
        status, body = await run_query(
            client,
            question="agent_alice가 최근 무엇을 했나요?",
            subject_agent="agent_alice",
            max_citations=10,
            strict_mode=False,
        )
        assert status == 200, body

        assert body["is_cold_start"] is False, "reflection이 landing됐으므로 cold-start가 아니어야 함"
        assert body["used_fallback"] is False, "smart mock narrative는 유효한 인용을 포함해야 함"
        assert len(body["answer"]) > 0, "answer가 비어 있으면 안 됩니다"
        assert len(body["citations"]) > 0, "citations이 비어 있으면 안 됩니다"
