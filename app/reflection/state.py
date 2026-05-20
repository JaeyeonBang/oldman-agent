"""Reflection trigger state — Phase 2.1.

ReflectionTriggerState: scope/subject 별 반성 트리거 조건 계산.
새 스키마 없이 기존 reflections + events + entities_episodic 테이블에서 계산.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb


@dataclass(frozen=True)
class ReflectionTriggerState:
    """특정 (scope, subject) 쌍의 트리거 조건 상태.

    Attributes:
        scope: 'agent' | 'pair' | 'society'
        subject: scope에 따른 식별자.
            agent → agent_id 문자열
            pair  → "observer:observed" 형식
            society → "global"
        events_since_last_reflection: 마지막 reflection 이후 해당 scope/subject
            관련 이벤트 수. reflection이 없으면 전체 이벤트 수.
        last_reflection_ts: 마지막 reflection의 타임스탬프. 없으면 None.
    """

    scope: str
    subject: str
    events_since_last_reflection: int
    last_reflection_ts: datetime | None


def get_trigger_state(
    conn: duckdb.DuckDBPyConnection,
    *,
    scope: str,
    subject: str,
) -> ReflectionTriggerState:
    """주어진 (scope, subject)에 대한 트리거 상태를 계산한다.

    스키마 변경 없이 기존 테이블에서 O(N) 계산.
    데모 스케일(5-20 에이전트)에서 성능 충분.
    """
    # 1. 가장 최근 reflection 타임스탬프 조회
    row = conn.execute(
        "SELECT MAX(ts) FROM reflections WHERE scope = ? AND subject = ?",
        [scope, subject],
    ).fetchone()
    last_reflection_ts: datetime | None = row[0] if row else None

    # 2. scope별 이벤트 카운트 쿼리
    event_count = _count_events_since(conn, scope=scope, subject=subject, since=last_reflection_ts)

    return ReflectionTriggerState(
        scope=scope,
        subject=subject,
        events_since_last_reflection=event_count,
        last_reflection_ts=last_reflection_ts,
    )


def _count_events_since(
    conn: duckdb.DuckDBPyConnection,
    *,
    scope: str,
    subject: str,
    since: datetime | None,
) -> int:
    """scope/subject 조건에 맞는 이벤트 수를 반환한다.

    scope=agent: events.source_agent == subject (이벤트를 보낸 에이전트)
    scope=pair:  entities_episodic.observer_agent == observer AND observed_agent == observed
    scope=society: 전체 events (since 이후)
    """
    if scope == "agent":
        if since is None:
            row = conn.execute(
                "SELECT COUNT(*) FROM events WHERE source_agent = ?",
                [subject],
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM events WHERE source_agent = ? AND ts > ?",
                [subject, since],
            ).fetchone()

    elif scope == "pair":
        # subject 형식: "observer_agent:observed_agent"
        parts = subject.split(":", 1)
        observer, observed = parts[0], parts[1]
        if since is None:
            row = conn.execute(
                "SELECT COUNT(*) FROM entities_episodic "
                "WHERE observer_agent = ? AND observed_agent = ?",
                [observer, observed],
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM entities_episodic "
                "WHERE observer_agent = ? AND observed_agent = ? AND ts > ?",
                [observer, observed, since],
            ).fetchone()

    elif scope == "society":
        if since is None:
            row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM events WHERE ts > ?", [since]
            ).fetchone()

    else:
        raise ValueError(f"알 수 없는 scope: {scope!r}")

    return int(row[0]) if row else 0
