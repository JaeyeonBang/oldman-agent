"""Phase 3.1 — RED tests: evidence selector."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import duckdb


def _insert_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    source_agent: str = "agent_alice",
    kind: str = "observation",
    ts: datetime | None = None,
    payload: dict | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    ts = ts or datetime.now(UTC)
    payload = payload or {"msg": "test"}
    conn.execute(
        "INSERT INTO events (event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (?, ?, ?, ?, 'self', ?, ?)",
        [event_id, ts, kind, source_agent, json.dumps(payload), uuid.uuid4().hex],
    )
    return event_id


def _insert_reflection(
    conn: duckdb.DuckDBPyConnection,
    *,
    scope: str = "agent",
    subject: str = "agent_alice",
    ts: datetime | None = None,
    text: str = "test reflection",
) -> str:
    rid = str(uuid.uuid4())
    ts = ts or datetime.now(UTC)
    conn.execute(
        "INSERT INTO reflections "
        "(reflection_id, ts, scope, subject, text, event_range_start, event_range_end, source_event_ids) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [rid, ts, scope, subject, text, ts, ts, "[]"],
    )
    return rid


class TestSelectEvidence:
    def test_select_evidence_empty_db_returns_empty(self, tmp_db: duckdb.DuckDBPyConnection) -> None:
        from app.narrative.evidence import select_evidence

        ev = select_evidence(tmp_db, subject_agent=None)
        assert ev.events == []
        assert ev.reflections == []

    def test_select_evidence_subject_filter_restricts_to_agent(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.evidence import select_evidence

        _insert_event(tmp_db, source_agent="agent_alice")
        _insert_event(tmp_db, source_agent="agent_bob")

        ev = select_evidence(tmp_db, subject_agent="agent_alice")
        assert len(ev.events) == 1
        assert ev.events[0].source_agent == "agent_alice"

    def test_select_evidence_no_subject_returns_society_wide(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.evidence import select_evidence

        _insert_event(tmp_db, source_agent="agent_alice")
        _insert_event(tmp_db, source_agent="agent_bob")

        ev = select_evidence(tmp_db, subject_agent=None)
        assert len(ev.events) == 2

    def test_select_evidence_orders_newest_first(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.evidence import select_evidence

        now = datetime.now(UTC)
        older = now - timedelta(hours=2)
        newer = now - timedelta(hours=1)

        _insert_event(tmp_db, source_agent="agent_alice", ts=older)
        _insert_event(tmp_db, source_agent="agent_alice", ts=newer)

        ev = select_evidence(tmp_db, subject_agent="agent_alice")
        assert len(ev.events) == 2
        # newest first
        assert ev.events[0].ts >= ev.events[1].ts

    def test_select_evidence_caps_at_max_events(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.evidence import select_evidence

        for i in range(10):
            _insert_event(tmp_db, source_agent="agent_alice", payload={"i": i})

        ev = select_evidence(tmp_db, subject_agent="agent_alice", max_events=3)
        assert len(ev.events) == 3

    def test_select_evidence_reflections_subject_filter(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.evidence import select_evidence

        _insert_reflection(tmp_db, scope="agent", subject="agent_alice")
        _insert_reflection(tmp_db, scope="agent", subject="agent_bob")

        ev = select_evidence(tmp_db, subject_agent="agent_alice")
        assert len(ev.reflections) == 1
        assert ev.reflections[0].subject == "agent_alice"

    def test_select_evidence_reflections_no_subject_returns_all(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.evidence import select_evidence

        _insert_reflection(tmp_db, scope="agent", subject="agent_alice")
        _insert_reflection(tmp_db, scope="society", subject="global")

        ev = select_evidence(tmp_db, subject_agent=None)
        assert len(ev.reflections) == 2
