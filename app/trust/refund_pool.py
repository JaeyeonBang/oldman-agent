"""환불 풀 — 수수료 적립 + claim 판정 + 배상 (P4 잔여).

제도적 신뢰의 보험 모델 (research/agent-trust-impl-plan-2026-07.md §1.3):
정산된 query마다 수수료가 마을 풀(village_pool 계정)에 쌓이고, 나쁜 정보에
당한 구매자가 claim을 걸면 꼰대가 판정해 query_price를 배상한다.

판정 입력 ``justified``는 호출자가 공급한다 — grounding 감사 결과나 운영자
판단. LLM을 단독 심판으로 쓰지 않는 원칙 (1차 리서치 §2.4)의 구조적 반영.

풀은 별도 원장이 아니라 credits 계정 — 자산 보존이 credits invariant로 검증.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import duckdb

from app.config import Settings
from app.credits.ledger import CreditsTransaction
from app.credits.ledger import transfer as credits_transfer

OLDMAN_TREASURY_AGENT_ID = "oldman"
VILLAGE_POOL_AGENT_ID = "village_pool"


class ClaimError(Exception):
    """존재하지 않는 invoice, 미정산 invoice, 또는 이미 판정된 claim."""


@dataclass(frozen=True)
class ClaimDecision:
    claim_id: str
    status: Literal["approved", "denied"]
    payout: int


def accrue_pool_fee(
    conn: duckdb.DuckDBPyConnection,
    settings: Settings,
    *,
    invoice_id: str,
    now: datetime,
) -> CreditsTransaction | None:
    """정산된 query 1건의 풀 수수료 적립 (자체 TX). fee<=0이면 no-op."""
    if settings.refund_pool_fee <= 0:
        return None
    try:
        conn.execute("BEGIN")
        # 멱등 가드 — 같은 invoice에 이미 pool_fee가 적립됐으면 no-op. 재시도
        # 경로가 생겨도 이중 적립을 막는다 (M4).
        already = conn.execute(
            "SELECT 1 FROM credits_transactions "
            "WHERE invoice_id = ? AND reason = 'pool_fee' AND outcome = 'applied'",
            [invoice_id],
        ).fetchone()
        if already is not None:
            conn.execute("COMMIT")
            return None
        tx = credits_transfer(
            conn,
            from_agent=OLDMAN_TREASURY_AGENT_ID,
            to_agent=VILLAGE_POOL_AGENT_ID,
            amount=settings.refund_pool_fee,
            reason="pool_fee",
            invoice_id=invoice_id,
            starting_grant=settings.starting_grant,
        )
        conn.execute("COMMIT")
    except Exception:
        with contextlib.suppress(duckdb.Error):
            conn.execute("ROLLBACK")
        raise
    return tx


def file_claim(
    conn: duckdb.DuckDBPyConnection,
    *,
    claimant_agent: str,
    invoice_id: str,
    reason_text: str,
    now: datetime,
) -> str:
    """정산된 invoice에 대한 배상 claim 접수 → claim_id."""
    row = conn.execute(
        "SELECT status FROM invoices WHERE invoice_id = ?", [invoice_id]
    ).fetchone()
    if row is None:
        raise ClaimError(f"unknown invoice: {invoice_id}")
    if row[0] != "settled":
        raise ClaimError(f"invoice not settled (status={row[0]!r}): {invoice_id}")

    claim_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO refund_claims "
        "(claim_id, invoice_id, claimant_agent, reason_text, status, filed_ts) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        [claim_id, invoice_id, claimant_agent, reason_text, now],
    )
    return claim_id


def adjudicate_claim(
    conn: duckdb.DuckDBPyConnection,
    settings: Settings,
    *,
    claim_id: str,
    justified: bool,
    now: datetime,
) -> ClaimDecision:
    """claim 판정 실행 (자체 TX). 승인 시 풀 → 구매자 query_price 배상."""
    row = conn.execute(
        "SELECT claimant_agent, invoice_id, status FROM refund_claims "
        "WHERE claim_id = ?",
        [claim_id],
    ).fetchone()
    if row is None:
        raise ClaimError(f"unknown claim: {claim_id}")
    claimant, invoice_id, status = row[0], row[1], row[2]
    if status != "pending":
        raise ClaimError(f"claim already adjudicated (status={status!r}): {claim_id}")

    try:
        conn.execute("BEGIN")
        # UPDATE에 status='pending' 가드 + RETURNING — pre-check와 UPDATE 사이에
        # 동시 판정이 끼어들면(sync route는 threadpool에서 진짜 동시성) 레이스
        # 패자를 거부해 이중 배상을 막는다 (M3, invoices.mark_invoice_settled와 동일 패턴).
        if justified:
            tx = credits_transfer(
                conn,
                from_agent=VILLAGE_POOL_AGENT_ID,
                to_agent=claimant,
                amount=settings.query_price,
                reason="refund_payout",
                invoice_id=str(invoice_id),
                starting_grant=settings.starting_grant,
            )
            won = conn.execute(
                "UPDATE refund_claims SET status='approved', decided_ts=?, "
                "payout_tx_id=? WHERE claim_id = ? AND status='pending' "
                "RETURNING claim_id",
                [now, tx.tx_id, claim_id],
            ).fetchone()
            if won is None:
                raise ClaimError(f"claim adjudication lost race: {claim_id}")
            decision = ClaimDecision(
                claim_id=claim_id, status="approved", payout=settings.query_price
            )
        else:
            won = conn.execute(
                "UPDATE refund_claims SET status='denied', decided_ts=? "
                "WHERE claim_id = ? AND status='pending' RETURNING claim_id",
                [now, claim_id],
            ).fetchone()
            if won is None:
                raise ClaimError(f"claim adjudication lost race: {claim_id}")
            decision = ClaimDecision(claim_id=claim_id, status="denied", payout=0)
        conn.execute("COMMIT")
    except Exception:
        with contextlib.suppress(duckdb.Error):
            conn.execute("ROLLBACK")
        raise
    return decision
