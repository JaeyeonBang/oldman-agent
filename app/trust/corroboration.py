"""모순/교차확인 오라클 — honesty 축의 corroboration 채널 (개선 ①).

devil's advocate C1이 요구한 '판매자 정직성의 실존 채널' 중 canary(P3)에
이은 두 번째:

  - ``record_contradiction``: 후속 사료가 기존 사료와 모순 → 판매자 honesty
    **소급 하향** + open escrow **몰수** — 조작 정보는 deferred 수익까지 잃는다.
  - ``record_corroboration``: **독립 판매자**의 교차 확인 → 원 판매자 honesty
    소폭 상향 (weight 0.5 — canary보다 약한 신호). self-corroboration은 거부:
    같은 답에 보상하는 순진한 corroboration은 output-agreement 함정(에코 보상,
    2차 리서치 §1.1)이므로, 최소 방어로 판매자 독립성을 강제한다. novelty
    (surprise) 가중은 후속 (SP/BTS, P5).

모순/확인의 *판정*은 호출자(운영자·검증 파이프라인)가 공급한다 — LLM 단독
심판 금지 원칙. 이 모듈은 판정의 *집행*만 한다.

트랜잭션 노트: escrow 몰수(단문 autocommit)와 trust event(자체 TX)는 별개
커밋 — 사이에서 죽으면 몰수만 반영될 수 있다 (자산은 보존됨: 몰수는 이체가
아니라 지급 취소라 audit invariant를 깨지 않는다).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb

from app.trust.service import TrustUpdateResult, record_trust_event

CORROBORATION_WEIGHT = 0.5


class CorroborationError(Exception):
    """존재하지 않는 event, 동일 event 쌍, 또는 self-corroboration."""


@dataclass(frozen=True)
class ContradictionResult:
    disputed_event_id: str
    seller_agent: str
    escrow_revoked: bool
    trust: TrustUpdateResult


def _seller_of(conn: duckdb.DuckDBPyConnection, event_id: str) -> str:
    row = conn.execute(
        "SELECT source_agent FROM events WHERE event_id = ?", [event_id]
    ).fetchone()
    if row is None:
        raise CorroborationError(f"unknown event: {event_id}")
    return str(row[0])


def record_contradiction(
    conn: duckdb.DuckDBPyConnection,
    *,
    disputed_event_id: str,
    contradicting_event_id: str,
    now: datetime,
    weight: float = 1.0,
) -> ContradictionResult:
    """모순 판정 집행: 소급 honesty 하향 + open escrow 몰수."""
    if disputed_event_id == contradicting_event_id:
        raise CorroborationError("disputed and contradicting must be distinct events")
    seller = _seller_of(conn, disputed_event_id)
    _seller_of(conn, contradicting_event_id)  # 존재 검증

    revoked = (
        conn.execute(
            "UPDATE royalty_escrows SET status='expired' "
            "WHERE event_id = ? AND status = 'open' RETURNING event_id",
            [disputed_event_id],
        ).fetchone()
        is not None
    )

    trust = record_trust_event(
        conn,
        agent_id=seller,
        criterion="honesty",
        positive=False,
        weight=weight,
        cause="grounding_contradiction",
        cause_ref=disputed_event_id,
        now=now,
    )
    return ContradictionResult(
        disputed_event_id=disputed_event_id,
        seller_agent=seller,
        escrow_revoked=revoked,
        trust=trust,
    )


def record_corroboration(
    conn: duckdb.DuckDBPyConnection,
    *,
    original_event_id: str,
    corroborating_event_id: str,
    now: datetime,
    weight: float = CORROBORATION_WEIGHT,
) -> TrustUpdateResult:
    """교차확인 판정 집행: 원 판매자 honesty 소폭 상향 (독립 판매자만)."""
    if original_event_id == corroborating_event_id:
        raise CorroborationError("original and corroborating must be distinct events")
    original_seller = _seller_of(conn, original_event_id)
    corroborating_seller = _seller_of(conn, corroborating_event_id)
    if original_seller == corroborating_seller:
        raise CorroborationError(
            "self-corroboration rejected (copy-cat/output-agreement 방어)"
        )
    return record_trust_event(
        conn,
        agent_id=original_seller,
        criterion="honesty",
        positive=True,
        weight=weight,
        cause="corroborated",
        cause_ref=original_event_id,
        now=now,
    )
