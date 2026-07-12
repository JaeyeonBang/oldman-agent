"""P1 — record_trust_event 오케스트레이션 (decay + update + 상태 전이 + 저장).

시나리오: 가입(provisional) → 정직 누적(member 승격) → on-off 배신(강등) →
감쇠(오래된 증거는 잊힘). 모든 갱신은 trust_events에 원인 ref와 함께 기록.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb

from app.storage.trust import get_membership, get_trust_score
from app.trust.service import record_trust_event

T0 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def test_first_event_creates_provisional_membership(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    result = record_trust_event(
        tmp_db,
        agent_id="kimbot",
        criterion="reliability",
        positive=True,
        cause="publish_settled",
        cause_ref="evt-001",
        now=T0,
    )
    assert result.state == "provisional"  # 증거 1건 — 아직 "미지"
    member = get_membership(tmp_db, "kimbot")
    assert member is not None
    assert member.state == "provisional"
    stored = get_trust_score(tmp_db, "kimbot", "reliability")
    assert stored is not None
    row = tmp_db.execute(
        "SELECT cause, cause_ref FROM trust_events WHERE agent_id = 'kimbot'"
    ).fetchone()
    assert row == ("publish_settled", "evt-001")


def test_promotion_after_sustained_honesty(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    for i in range(6):
        result = record_trust_event(
            tmp_db,
            agent_id="kimbot",
            criterion="reliability",
            positive=True,
            cause="publish_settled",
            cause_ref=f"evt-{i}",
            now=T0 + timedelta(hours=i),
        )
    assert result.state == "member"


def test_on_off_attacker_demoted_fast(tmp_db: duckdb.DuckDBPyConnection) -> None:
    """느리게 얻은 신뢰가 배신 3회에 무너진다 — 비대칭 동역학의 통합 검증."""
    for i in range(6):
        record_trust_event(
            tmp_db,
            agent_id="onoff",
            criterion="reliability",
            positive=True,
            cause="publish_settled",
            cause_ref=f"good-{i}",
            now=T0 + timedelta(hours=i),
        )
    for i in range(3):
        result = record_trust_event(
            tmp_db,
            agent_id="onoff",
            criterion="reliability",
            positive=False,
            cause="grounding_contradiction",
            cause_ref=f"bad-{i}",
            now=T0 + timedelta(hours=6 + i),
        )
    assert result.state in ("penalized", "excluded")
    assert result.violation_count == 3


def test_decay_applied_between_events(tmp_db: duckdb.DuckDBPyConnection) -> None:
    record_trust_event(
        tmp_db,
        agent_id="oldtimer",
        criterion="reliability",
        positive=True,
        weight=10.0,
        cause="publish_settled",
        cause_ref="big-sale",
        now=T0,
    )
    # 반감기(30일) 경과 후 재등장 — 과거 증거는 절반으로
    result = record_trust_event(
        tmp_db,
        agent_id="oldtimer",
        criterion="reliability",
        positive=True,
        cause="publish_settled",
        cause_ref="comeback",
        now=T0 + timedelta(days=30),
    )
    # 무감쇠였다면 Beta(12,3) mean=0.8 — 감쇠로 그보다 낮아야 함
    assert result.score.mean < 0.75
