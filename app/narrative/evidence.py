"""Evidence 선택기 — Phase 3.1.

DB에서 이벤트·reflection을 조회해 ``Evidence`` 묶음으로 반환한다.
subject_agent 지정 시 해당 에이전트 관련 데이터만, None이면 전체 소사이어티.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb


@dataclass(frozen=True)
class EventRow:
    """events 테이블 단일 행."""

    event_id: str
    ts: datetime
    kind: str
    source_agent: str
    source_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ReflectionRow:
    """reflections 테이블 단일 행."""

    reflection_id: str
    ts: datetime
    scope: str
    subject: str
    text: str


@dataclass(frozen=True)
class Evidence:
    """select_evidence가 반환하는 증거 묶음 (불변)."""

    events: list[EventRow]
    reflections: list[ReflectionRow]


def select_evidence(
    conn: duckdb.DuckDBPyConnection,
    subject_agent: str | None,
    max_events: int = 30,
    max_reflections: int = 20,
) -> Evidence:
    """DB에서 evidence를 선택한다.

    Args:
        conn: DuckDB 연결.
        subject_agent: None이면 전체 소사이어티, 지정 시 해당 에이전트 필터.
        max_events: 최대 이벤트 수 (최신순).
        max_reflections: 최대 reflection 수 (최신순).

    Returns:
        Evidence 불변 객체.
    """
    events = _select_events(conn, subject_agent=subject_agent, limit=max_events)
    reflections = _select_reflections(
        conn, subject_agent=subject_agent, limit=max_reflections
    )
    return Evidence(events=events, reflections=reflections)


def _select_events(
    conn: duckdb.DuckDBPyConnection,
    subject_agent: str | None,
    limit: int,
) -> list[EventRow]:
    if subject_agent is not None:
        rows = conn.execute(
            "SELECT event_id, ts, kind, source_agent, source_type, payload_json "
            "FROM events "
            "WHERE source_agent = ? "
            "ORDER BY ts DESC LIMIT ?",
            [subject_agent, limit],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT event_id, ts, kind, source_agent, source_type, payload_json "
            "FROM events "
            "ORDER BY ts DESC LIMIT ?",
            [limit],
        ).fetchall()

    result: list[EventRow] = []
    for event_id, ts, kind, source_agent, source_type, payload_json in rows:
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        except (json.JSONDecodeError, TypeError):
            payload = {}
        result.append(
            EventRow(
                event_id=str(event_id),
                ts=ts,
                kind=kind,
                source_agent=source_agent,
                source_type=source_type,
                payload=payload,
            )
        )
    return result


def _select_reflections(
    conn: duckdb.DuckDBPyConnection,
    subject_agent: str | None,
    limit: int,
) -> list[ReflectionRow]:
    if subject_agent is not None:
        rows = conn.execute(
            "SELECT reflection_id, ts, scope, subject, text "
            "FROM reflections "
            "WHERE (scope = 'agent' AND subject = ?) "
            "   OR (scope = 'pair' AND (subject LIKE ? OR subject LIKE ?)) "
            "ORDER BY ts DESC LIMIT ?",
            [
                subject_agent,
                f"{subject_agent}:%",
                f"%:{subject_agent}",
                limit,
            ],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT reflection_id, ts, scope, subject, text "
            "FROM reflections "
            "ORDER BY ts DESC LIMIT ?",
            [limit],
        ).fetchall()

    return [
        ReflectionRow(
            reflection_id=str(rid),
            ts=ts,
            scope=scope,
            subject=subject,
            text=text,
        )
        for rid, ts, scope, subject, text in rows
    ]
