"""Phase 2.1 — RED tests: ReflectionTriggerState + get_trigger_state.

TDD cycle: 이 파일을 먼저 작성하고 app/reflection/state.py 구현 전에 실패해야 함.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import duckdb

from app.reflection.state import ReflectionTriggerState, get_trigger_state

# ── helpers ──────────────────────────────────────────────────────────────────

def _insert_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    source_agent: str,
    ts: datetime,
    observed_agent: str | None = None,
    kind: str = "observation",
    payload: dict | None = None,
) -> str:
    """Insert a minimal event row bypassing the API layer."""
    import json

    event_id = str(uuid.uuid4())
    p_hash = str(uuid.uuid4())  # 단순 유일성 보장
    payload_json = json.dumps(payload or {"msg": "test"})
    conn.execute(
        "INSERT INTO events (event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (?, ?, ?, ?, 'self', ?, ?)",
        [event_id, ts, kind, source_agent, payload_json, p_hash],
    )
    # entities_episodic 도 삽입 (pair-scope 필터링 테스트용)
    conn.execute(
        "INSERT INTO entities_episodic (id, event_id, observer_agent, observed_agent, kind, ts, source_type) "
        "VALUES (?, ?, ?, ?, ?, ?, 'self')",
        [str(uuid.uuid4()), event_id, source_agent, observed_agent, kind, ts],
    )
    return event_id


def _insert_reflection(
    conn: duckdb.DuckDBPyConnection,
    *,
    scope: str,
    subject: str,
    ts: datetime,
    event_ids: list[str] | None = None,
) -> str:
    """Insert a minimal reflections row."""
    import json

    reflection_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO reflections "
        "(reflection_id, ts, scope, subject, text, event_range_start, event_range_end, source_event_ids) "
        "VALUES (?, ?, ?, ?, 'test reflection', ?, ?, ?)",
        [
            reflection_id,
            ts,
            scope,
            subject,
            ts - timedelta(hours=1),
            ts,
            json.dumps(event_ids or []),
        ],
    )
    return reflection_id


# ── tests ────────────────────────────────────────────────────────────────────

class TestReflectionTriggerStateEmpty:
    """빈 DB에서 trigger state 반환값 확인."""

    def test_trigger_state_empty_db_returns_zero_counts(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        state = get_trigger_state(tmp_db, scope="agent", subject="agent_alice")

        assert isinstance(state, ReflectionTriggerState)
        assert state.events_since_last_reflection == 0
        assert state.last_reflection_ts is None

    def test_trigger_state_society_scope_empty_returns_zero(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        state = get_trigger_state(tmp_db, scope="society", subject="global")
        assert state.events_since_last_reflection == 0
        assert state.last_reflection_ts is None


class TestReflectionTriggerStateWithEvents:
    """이벤트가 있을 때 카운트 동작 확인."""

    def test_trigger_state_counts_events_since_last_reflection(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        base_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        # reflection 이전 이벤트 3개
        for i in range(3):
            _insert_event(
                tmp_db,
                source_agent="agent_alice",
                ts=base_ts + timedelta(minutes=i),
            )
        reflection_ts = base_ts + timedelta(hours=1)
        _insert_reflection(
            tmp_db, scope="agent", subject="agent_alice", ts=reflection_ts
        )
        # reflection 이후 이벤트 5개
        for i in range(5):
            _insert_event(
                tmp_db,
                source_agent="agent_alice",
                ts=reflection_ts + timedelta(minutes=i + 1),
            )

        state = get_trigger_state(tmp_db, scope="agent", subject="agent_alice")

        assert state.events_since_last_reflection == 5
        assert state.last_reflection_ts is not None

    def test_trigger_state_no_reflection_counts_all_events(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        base_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        for i in range(7):
            _insert_event(
                tmp_db,
                source_agent="agent_bob",
                ts=base_ts + timedelta(minutes=i),
            )

        state = get_trigger_state(tmp_db, scope="agent", subject="agent_bob")
        assert state.events_since_last_reflection == 7
        assert state.last_reflection_ts is None

    def test_trigger_state_pair_scope_filters_observer_and_observed(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        base_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        # alice→bob 페어 이벤트 4개
        for i in range(4):
            _insert_event(
                tmp_db,
                source_agent="agent_alice",
                observed_agent="agent_bob",
                ts=base_ts + timedelta(minutes=i),
            )
        # alice→charlie 이벤트 2개 (다른 페어 — 제외돼야 함)
        for i in range(2):
            _insert_event(
                tmp_db,
                source_agent="agent_alice",
                observed_agent="agent_charlie",
                ts=base_ts + timedelta(minutes=10 + i),
            )

        # pair scope subject 형식: "agent_alice:agent_bob"
        state = get_trigger_state(
            tmp_db, scope="pair", subject="agent_alice:agent_bob"
        )
        assert state.events_since_last_reflection == 4

    def test_trigger_state_society_scope_counts_all_events(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        base_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        _insert_event(
            tmp_db, source_agent="agent_alice", ts=base_ts + timedelta(minutes=1)
        )
        _insert_event(
            tmp_db, source_agent="agent_bob", ts=base_ts + timedelta(minutes=2)
        )
        _insert_event(
            tmp_db, source_agent="agent_charlie", ts=base_ts + timedelta(minutes=3)
        )

        state = get_trigger_state(tmp_db, scope="society", subject="global")
        assert state.events_since_last_reflection == 3
