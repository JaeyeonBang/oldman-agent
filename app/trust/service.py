"""record_trust_event — P1 오케스트레이션 (decay → update → 전이 → 저장).

P2(정산 royalty)·P3(canary 감사)가 호출하는 단일 진입점. 자체 트랜잭션을
관리한다 (publish TX 밖의 독립 경로).

honesty 축 주의: P3 canary 오라클 가동 전까지 publish 경로는 reliability만
갱신한다 — "전구 없는 온도계" 금지 (plan §3 P1).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb

from app.storage.trust import (
    append_trust_event,
    get_membership,
    get_trust_score,
    upsert_membership,
    upsert_trust_score,
)
from app.trust.ledger import (
    COLD_START_PRIOR,
    BetaScore,
    LedgerPolicy,
    decay,
    update,
)
from app.trust.ledger import (
    DEFAULT_POLICY as DEFAULT_LEDGER_POLICY,
)
from app.trust.membership import (
    DEFAULT_POLICY as DEFAULT_MEMBERSHIP_POLICY,
)
from app.trust.membership import (
    MembershipPolicy,
    MembershipState,
    evaluate_transition,
)


@dataclass(frozen=True)
class TrustUpdateResult:
    agent_id: str
    criterion: str
    score: BetaScore
    state: MembershipState
    violation_count: int


def record_trust_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    agent_id: str,
    criterion: str,
    positive: bool,
    weight: float = 1.0,
    cause: str,
    cause_ref: str | None = None,
    now: datetime | None = None,
    ledger_policy: LedgerPolicy = DEFAULT_LEDGER_POLICY,
    membership_policy: MembershipPolicy = DEFAULT_MEMBERSHIP_POLICY,
) -> TrustUpdateResult:
    """신뢰 증거 1건 반영: 감쇠 적용 → 비대칭 update → 멤버십 전이 → 저장.

    부정 증거는 violation_count를 1 올린다 (회복 bar 상승 + 축출 임계).
    """
    ts = now or datetime.now(UTC)
    try:
        conn.execute("BEGIN")

        member = get_membership(conn, agent_id)
        if member is None:
            joined_at = ts
            prev_state: MembershipState = "provisional"
            violations = 0
        else:
            joined_at = member.joined_at
            prev_state = member.state
            violations = member.violation_count

        stored = get_trust_score(conn, agent_id, criterion)
        if stored is None:
            score = COLD_START_PRIOR
        else:
            prev_score, last_ts = stored
            elapsed_days = max(0.0, (ts - last_ts).total_seconds() / 86400.0)
            score = decay(
                prev_score,
                elapsed_days=elapsed_days,
                half_life_days=ledger_policy.half_life_for(criterion),
            )
        score = update(score, positive=positive, weight=weight, policy=ledger_policy)

        if not positive:
            violations += 1

        new_state = evaluate_transition(
            state=prev_state,
            score_lower=score.lower_bound(),
            observations=score.observations,
            violation_count=violations,
            policy=membership_policy,
        )

        upsert_trust_score(
            conn, agent_id=agent_id, criterion=criterion, score=score, ts=ts
        )
        append_trust_event(
            conn,
            agent_id=agent_id,
            criterion=criterion,
            positive=positive,
            weight=weight,
            cause=cause,
            cause_ref=cause_ref,
            ts=ts,
        )
        upsert_membership(
            conn,
            agent_id=agent_id,
            state=new_state,
            violation_count=violations,
            joined_at=joined_at,
            state_changed_at=ts if new_state != prev_state else joined_at,
        )
        conn.execute("COMMIT")
    except Exception:
        with contextlib.suppress(duckdb.Error):
            conn.execute("ROLLBACK")
        raise

    return TrustUpdateResult(
        agent_id=agent_id,
        criterion=criterion,
        score=score,
        state=new_state,
        violation_count=violations,
    )
