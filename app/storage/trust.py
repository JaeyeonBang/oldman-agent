"""trust_ledger / village_registry / trust_events 저장 helpers (P1).

트랜잭션 관리 없음 — 호출자(app/trust/service.py)가 BEGIN/COMMIT을 감싼다
(publish 경로와 동일한 규율). 모든 점수 갱신은 trust_events에 원인 ref와
함께 append — "점수의 citation".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb

from app.trust.ledger import BetaScore
from app.trust.membership import MembershipState


@dataclass(frozen=True)
class MembershipRow:
    agent_id: str
    state: MembershipState
    violation_count: int
    joined_at: datetime
    state_changed_at: datetime


def _aware(ts: datetime) -> datetime:
    """DuckDB TIMESTAMP는 naive로 돌아온다 — UTC로 통일."""
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


def get_trust_score(
    conn: duckdb.DuckDBPyConnection, agent_id: str, criterion: str
) -> tuple[BetaScore, datetime] | None:
    row = conn.execute(
        "SELECT alpha, beta, last_update_ts FROM trust_ledger "
        "WHERE agent_id = ? AND criterion = ?",
        [agent_id, criterion],
    ).fetchone()
    if row is None:
        return None
    return BetaScore(alpha=row[0], beta=row[1]), _aware(row[2])


def upsert_trust_score(
    conn: duckdb.DuckDBPyConnection,
    *,
    agent_id: str,
    criterion: str,
    score: BetaScore,
    ts: datetime,
) -> None:
    conn.execute(
        "INSERT INTO trust_ledger (agent_id, criterion, alpha, beta, last_update_ts) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (agent_id, criterion) DO UPDATE SET "
        "alpha = excluded.alpha, beta = excluded.beta, "
        "last_update_ts = excluded.last_update_ts",
        [agent_id, criterion, score.alpha, score.beta, ts],
    )


def append_trust_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    agent_id: str,
    criterion: str,
    positive: bool,
    weight: float,
    cause: str,
    cause_ref: str | None,
    ts: datetime,
) -> str:
    trust_event_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO trust_events "
        "(trust_event_id, ts, agent_id, criterion, positive, weight, cause, cause_ref) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [trust_event_id, ts, agent_id, criterion, positive, weight, cause, cause_ref],
    )
    return trust_event_id


def get_membership(
    conn: duckdb.DuckDBPyConnection, agent_id: str
) -> MembershipRow | None:
    row = conn.execute(
        "SELECT agent_id, state, violation_count, joined_at, state_changed_at "
        "FROM village_registry WHERE agent_id = ?",
        [agent_id],
    ).fetchone()
    if row is None:
        return None
    return MembershipRow(
        agent_id=row[0],
        state=row[1],
        violation_count=row[2],
        joined_at=_aware(row[3]),
        state_changed_at=_aware(row[4]),
    )


def upsert_membership(
    conn: duckdb.DuckDBPyConnection,
    *,
    agent_id: str,
    state: MembershipState,
    violation_count: int,
    joined_at: datetime,
    state_changed_at: datetime,
) -> None:
    conn.execute(
        "INSERT INTO village_registry "
        "(agent_id, state, violation_count, joined_at, state_changed_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (agent_id) DO UPDATE SET "
        "state = excluded.state, violation_count = excluded.violation_count, "
        "state_changed_at = excluded.state_changed_at",
        [agent_id, state, violation_count, joined_at, state_changed_at],
    )
