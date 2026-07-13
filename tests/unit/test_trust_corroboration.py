"""개선 ① — 모순/교차확인 오라클 (TDD).

honesty 축의 canary 외 실존 채널 (devil's advocate C1):
  - 모순: 후속 사료가 기존 사료를 뒤집으면 판매자 honesty 소급 하향 +
    open escrow 몰수 (조작 정보의 deferred 수익 차단)
  - 교차확인: 독립 판매자의 확인 → 원 판매자 honesty 소폭 상향.
    self-corroboration은 거부 (copy-cat/output-agreement 함정 방어)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import duckdb
import pytest

from app.config import Settings
from app.storage.events import insert_event
from app.trust.corroboration import (
    CorroborationError,
    record_contradiction,
    record_corroboration,
)
from app.trust.payout import split_publish_payment

T0 = datetime(2026, 7, 13, 15, 0, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(
        db_path=":memory:",
        jaccard_window=50,
        jaccard_threshold=0.9,
        payment_enabled=True,
        royalty_enabled=True,
        publish_reward=5,
        starting_grant=100,
    )


def _insert_event(
    conn: duckdb.DuckDBPyConnection, seller: str, text: str
) -> str:
    event_id = str(uuid.uuid4())
    insert_event(
        conn,
        event_id=event_id,
        ts=T0,
        kind="anecdote",
        source_agent=seller,
        source_type="third_party",
        payload={"text": text},
        payload_hash=str(uuid.uuid4()),  # 테스트용 유니크 해시
    )
    return event_id


def test_contradiction_downgrades_seller_and_revokes_escrow(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    settings = _settings()
    disputed = _insert_event(tmp_db, "kimbot", "이봇이 데이터셋을 공유했다")
    tmp_db.execute("BEGIN")
    split_publish_payment(
        tmp_db, settings, event_id=disputed, seller_agent="kimbot", now=T0
    )
    tmp_db.execute("COMMIT")
    contradicting = _insert_event(tmp_db, "leebot", "그날 이봇은 오프라인이었다")

    result = record_contradiction(
        tmp_db,
        disputed_event_id=disputed,
        contradicting_event_id=contradicting,
        now=T0,
    )
    assert result.seller_agent == "kimbot"
    assert result.escrow_revoked is True
    assert result.trust.violation_count == 1
    escrow = tmp_db.execute(
        "SELECT status FROM royalty_escrows WHERE event_id = ?", [disputed]
    ).fetchone()
    assert escrow == ("expired",)  # 몰수 — 인용돼도 지급 없음
    trust_row = tmp_db.execute(
        "SELECT criterion, positive, cause FROM trust_events WHERE agent_id='kimbot'"
    ).fetchone()
    assert trust_row == ("honesty", False, "grounding_contradiction")


def test_contradiction_requires_two_distinct_events(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    e1 = _insert_event(tmp_db, "kimbot", "사실 A")
    with pytest.raises(CorroborationError):
        record_contradiction(
            tmp_db, disputed_event_id=e1, contradicting_event_id=e1, now=T0
        )


def test_contradiction_unknown_event_raises(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    e1 = _insert_event(tmp_db, "kimbot", "사실 A")
    with pytest.raises(CorroborationError):
        record_contradiction(
            tmp_db,
            disputed_event_id=str(uuid.uuid4()),
            contradicting_event_id=e1,
            now=T0,
        )


def test_corroboration_rewards_original_seller(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    original = _insert_event(tmp_db, "kimbot", "이봇이 데이터셋을 공유했다")
    confirming = _insert_event(tmp_db, "leebot", "나도 그 공유를 봤다")
    result = record_corroboration(
        tmp_db,
        original_event_id=original,
        corroborating_event_id=confirming,
        now=T0,
    )
    assert result.agent_id == "kimbot"
    trust_row = tmp_db.execute(
        "SELECT criterion, positive, cause, weight FROM trust_events "
        "WHERE agent_id='kimbot'"
    ).fetchone()
    assert trust_row is not None
    assert trust_row[0] == "honesty"
    assert trust_row[1] is True
    assert trust_row[2] == "corroborated"
    assert trust_row[3] < 1.0  # canary보다 약한 신호


def test_self_corroboration_rejected(tmp_db: duckdb.DuckDBPyConnection) -> None:
    """copy-cat 함정: 같은 판매자의 자기 확인은 신호가 아니다."""
    e1 = _insert_event(tmp_db, "kimbot", "사실 A")
    e2 = _insert_event(tmp_db, "kimbot", "사실 A를 나도 확인했다")
    with pytest.raises(CorroborationError):
        record_corroboration(
            tmp_db, original_event_id=e1, corroborating_event_id=e2, now=T0
        )
