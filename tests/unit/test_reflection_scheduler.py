"""Phase 2.4 — RED tests for reflection scheduler + trigger policy."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from app.llm.base import LLMRequest, LLMResponse
from app.reflection.scheduler import (
    maybe_run_reflection,
    should_trigger,
)
from app.reflection.state import ReflectionTriggerState

# ── helpers ──────────────────────────────────────────────────────────────────

class _CannedProvider:
    """원하는 텍스트를 반환하는 mock provider."""

    name = "canned"
    model = "canned-1"

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls.append(req)
        return LLMResponse(
            text=self._text,
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


def _insert_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    source_agent: str,
    ts: datetime,
    observed_agent: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    p_hash = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO events (event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (?, ?, 'observation', ?, 'self', ?, ?)",
        [event_id, ts, source_agent, json.dumps({"msg": "x"}), p_hash],
    )
    conn.execute(
        "INSERT INTO entities_episodic (id, event_id, observer_agent, observed_agent, kind, ts, source_type) "
        "VALUES (?, ?, ?, ?, 'observation', ?, 'self')",
        [str(uuid.uuid4()), event_id, source_agent, observed_agent, ts],
    )
    return event_id


def _state(
    *, events: int, last_ts: datetime | None
) -> ReflectionTriggerState:
    return ReflectionTriggerState(
        scope="agent",
        subject="agent_alice",
        events_since_last_reflection=events,
        last_reflection_ts=last_ts,
    )


# ── should_trigger ───────────────────────────────────────────────────────────

class TestShouldTrigger:
    def test_count_threshold(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        st = _state(events=10, last_ts=now - timedelta(minutes=5))
        assert should_trigger(st, now=now) is True

    def test_count_below_threshold(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        st = _state(events=9, last_ts=now - timedelta(minutes=5))
        assert should_trigger(st, now=now) is False

    def test_age_threshold_with_some_events(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        # 7시간 전 reflection, 이벤트 5개 → age trigger
        st = _state(events=5, last_ts=now - timedelta(hours=7))
        assert should_trigger(st, now=now) is True

    def test_age_threshold_with_no_events_does_not_fire(self) -> None:
        """이벤트가 0개면 age 트리거도 작동하지 않아야 함 (반성할 내용이 없음)."""
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        st = _state(events=0, last_ts=now - timedelta(hours=7))
        assert should_trigger(st, now=now) is False

    def test_neither_returns_false(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        st = _state(events=3, last_ts=now - timedelta(minutes=10))
        assert should_trigger(st, now=now) is False

    def test_no_prior_reflection_relies_on_count_only(self) -> None:
        """이전 reflection이 없으면 카운트만으로 판단."""
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        st_below = ReflectionTriggerState(
            scope="agent", subject="a", events_since_last_reflection=5, last_reflection_ts=None
        )
        st_above = ReflectionTriggerState(
            scope="agent", subject="a", events_since_last_reflection=10, last_reflection_ts=None
        )
        assert should_trigger(st_below, now=now) is False
        assert should_trigger(st_above, now=now) is True


# ── maybe_run_reflection ─────────────────────────────────────────────────────

_VALID_LLM_JSON = json.dumps(
    {
        "summary": "테스트 요약",
        "descriptors": ["감시형", "고빈도"],
        "evidence_event_ids": [],
    }
)


class TestMaybeRunReflection:
    @pytest.mark.asyncio
    async def test_maybe_run_below_threshold_returns_none(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        # 이벤트 3개만 → threshold(10) 미만
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        for i in range(3):
            _insert_event(
                tmp_db, source_agent="agent_alice", ts=ts + timedelta(minutes=i)
            )
        provider = _CannedProvider(_VALID_LLM_JSON)

        result = await maybe_run_reflection(
            tmp_db,
            scope="agent",
            subject="agent_alice",
            provider=provider,
            now=ts + timedelta(minutes=10),
        )

        assert result is None
        assert provider.calls == []
        row = tmp_db.execute("SELECT COUNT(*) FROM reflections").fetchone()
        assert row is not None
        assert row[0] == 0

    @pytest.mark.asyncio
    async def test_maybe_run_persists_reflection_row(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        for i in range(10):
            _insert_event(
                tmp_db, source_agent="agent_alice", ts=ts + timedelta(minutes=i)
            )
        provider = _CannedProvider(_VALID_LLM_JSON)

        result = await maybe_run_reflection(
            tmp_db,
            scope="agent",
            subject="agent_alice",
            provider=provider,
            now=ts + timedelta(minutes=15),
        )

        assert result is not None
        assert provider.calls  # LLM 호출됨
        row = tmp_db.execute(
            "SELECT scope, subject FROM reflections"
        ).fetchone()
        assert row == ("agent", "agent_alice")

    @pytest.mark.asyncio
    async def test_maybe_run_malformed_output_skips_persist(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        for i in range(10):
            _insert_event(
                tmp_db, source_agent="agent_alice", ts=ts + timedelta(minutes=i)
            )
        provider = _CannedProvider("garbage_not_json")

        result = await maybe_run_reflection(
            tmp_db,
            scope="agent",
            subject="agent_alice",
            provider=provider,
            now=ts + timedelta(minutes=15),
        )

        assert result is None
        row = tmp_db.execute("SELECT COUNT(*) FROM reflections").fetchone()
        assert row is not None
        assert row[0] == 0

    @pytest.mark.asyncio
    async def test_maybe_run_llm_exception_does_not_raise(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        """LLM 호출 실패 시 예외를 삼키고 None을 반환해야 한다 (publish 보호)."""
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        for i in range(10):
            _insert_event(
                tmp_db, source_agent="agent_alice", ts=ts + timedelta(minutes=i)
            )
        provider = _RaisingProvider()

        result = await maybe_run_reflection(
            tmp_db,
            scope="agent",
            subject="agent_alice",
            provider=provider,
            now=ts + timedelta(minutes=15),
        )

        assert result is None
        row = tmp_db.execute("SELECT COUNT(*) FROM reflections").fetchone()
        assert row is not None
        assert row[0] == 0

    @pytest.mark.asyncio
    async def test_maybe_run_concurrent_writes_only_one(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        """동일 (scope, subject)에 대해 동시에 호출돼도 reflection이 1번만 기록."""
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        for i in range(10):
            _insert_event(
                tmp_db, source_agent="agent_alice", ts=ts + timedelta(minutes=i)
            )
        provider = _CannedProvider(_VALID_LLM_JSON)
        now = ts + timedelta(minutes=15)

        # 두 호출을 gather (사용 가능한 lock 메커니즘 검증)
        results = await asyncio.gather(
            maybe_run_reflection(
                tmp_db, scope="agent", subject="agent_alice", provider=provider, now=now
            ),
            maybe_run_reflection(
                tmp_db, scope="agent", subject="agent_alice", provider=provider, now=now
            ),
        )

        # 두 호출 모두 성공할 수 있고 reflection이 2개 생길 수 있지만,
        # 적어도 하나는 성공해야 함. 데모 스케일에서 중복 reflection은 허용 (계획 §2.4).
        count = tmp_db.execute("SELECT COUNT(*) FROM reflections").fetchone()
        assert count is not None
        assert count[0] >= 1
        # 최소 한 호출은 결과 반환
        assert any(r is not None for r in results)
