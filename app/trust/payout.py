"""층위 결제 — listing fee + citation royalty escrow (P2).

메커니즘 디자인 근거 (research/agent-trust-impl-plan-2026-07.md §1.1):
  - 소액 listing fee 즉시 지급: 보고 비용 보전 + cold-start 유동성
  - 잔액은 escrow: 유료 query에서 인용(``[↑eXX]``)되면 royalty로 해제 —
    inline citation이 곧 attribution 장부. 조작 정보는 인용되지 않아
    구조적으로 listing fee 이상 벌 수 없다 (deferred, usefulness-contingent)
  - horizon 경과 시 소멸: 에이전트가 미래 royalty를 0으로 할인하지 않도록
    유한 기한 (기본 14일)

escrow는 별도 계좌가 아니라 회계 기록 — credits는 인용 시점에 oldman
treasury에서 판매자로 이동한다 (자산 보존).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import duckdb

from app.config import Settings
from app.credits.ledger import transfer as credits_transfer

OLDMAN_TREASURY_AGENT_ID = "oldman"


@dataclass(frozen=True)
class PublishPayout:
    listing_fee_tx_id: str
    listing_fee: int
    escrowed: int


@dataclass(frozen=True)
class RoyaltyRelease:
    event_id: str
    seller_agent: str
    amount: int
    status: Literal["paid", "expired", "skipped_self_citation"]


def split_publish_payment(
    conn: duckdb.DuckDBPyConnection,
    settings: Settings,
    *,
    event_id: str,
    seller_agent: str,
    now: datetime,
) -> PublishPayout:
    """publish 매입 대금 분할. 호출자의 TX 안에서 실행 (publish 경로와 동일 규율).

    Raises:
        InsufficientFundsError: treasury가 listing fee를 감당 못 할 때
            (publish 경로가 OldmanInsufficientFundsError로 매핑).
    """
    reward = settings.publish_reward
    fee = min(reward, max(1, round(reward * settings.listing_fee_ratio)))
    tx = credits_transfer(
        conn,
        from_agent=OLDMAN_TREASURY_AGENT_ID,
        to_agent=seller_agent,
        amount=fee,
        reason="listing_fee",
        event_id=event_id,
        starting_grant=settings.starting_grant,
    )
    escrowed = reward - fee
    if escrowed > 0:
        conn.execute(
            "INSERT INTO royalty_escrows "
            "(event_id, seller_agent, amount, created_ts, expires_ts, status) "
            "VALUES (?, ?, ?, ?, ?, 'open')",
            [
                event_id,
                seller_agent,
                escrowed,
                now,
                now + timedelta(days=settings.escrow_horizon_days),
            ],
        )
    return PublishPayout(
        listing_fee_tx_id=tx.tx_id, listing_fee=fee, escrowed=escrowed
    )


def release_royalties_for_citations(
    conn: duckdb.DuckDBPyConnection,
    settings: Settings,
    *,
    citation_event_ids: list[str],
    invoice_id: str | None,
    now: datetime,
    querier_agent: str | None = None,
) -> list[RoyaltyRelease]:
    """유료 query의 citation에 대응하는 open escrow를 해제 (자체 TX).

    - 기한 내 인용 → royalty 지급 (oldman → seller, 원인 ref = invoice)
    - 기한 경과 → 소멸 (지급 없음)
    - open escrow 없는 citation → no-op (이중 지급 방지)
    - **자가 인용(querier==seller) → 스킵**: 조작 정보를 자기 query로 인용해
      escrow를 회수하는 self-dealing 차단 (F2). escrow는 open으로 남겨 미래
      독립 인용/만료를 기다린다. corroboration.py의 self-corroboration 거부와 동일 원리.
      잔여 한계: 단일 운영자가 별도 계정/DID로 인용하면 막지 못한다 — 외부
      operator 신원이 필요하며 자가운영 데모 범위 밖.
    """
    results: list[RoyaltyRelease] = []
    if not citation_event_ids:
        return results
    try:
        conn.execute("BEGIN")
        for event_id in dict.fromkeys(citation_event_ids):  # 순서 보존 dedup
            row = conn.execute(
                "SELECT seller_agent, amount, expires_ts FROM royalty_escrows "
                "WHERE event_id = ? AND status = 'open'",
                [event_id],
            ).fetchone()
            if row is None:
                continue
            seller, amount, expires_ts = row[0], int(row[1]), row[2]
            if querier_agent is not None and seller == querier_agent:
                # 자가 인용 — 방출하지 않고 escrow는 open 유지 (F2).
                results.append(
                    RoyaltyRelease(
                        event_id=event_id,
                        seller_agent=seller,
                        amount=amount,
                        status="skipped_self_citation",
                    )
                )
                continue
            if expires_ts.tzinfo is None:
                expires_ts = expires_ts.replace(tzinfo=now.tzinfo)
            if now > expires_ts:
                conn.execute(
                    "UPDATE royalty_escrows SET status='expired' WHERE event_id = ?",
                    [event_id],
                )
                results.append(
                    RoyaltyRelease(
                        event_id=event_id,
                        seller_agent=seller,
                        amount=amount,
                        status="expired",
                    )
                )
                continue
            tx = credits_transfer(
                conn,
                from_agent=OLDMAN_TREASURY_AGENT_ID,
                to_agent=seller,
                amount=amount,
                reason="royalty",
                event_id=event_id,
                invoice_id=invoice_id,
                starting_grant=settings.starting_grant,
            )
            conn.execute(
                "UPDATE royalty_escrows SET status='paid', paid_tx_id=?, paid_ts=? "
                "WHERE event_id = ?",
                [tx.tx_id, now, event_id],
            )
            results.append(
                RoyaltyRelease(
                    event_id=event_id,
                    seller_agent=seller,
                    amount=amount,
                    status="paid",
                )
            )
        conn.execute("COMMIT")
    except Exception:
        with contextlib.suppress(duckdb.Error):
            conn.execute("ROLLBACK")
        raise
    return results
