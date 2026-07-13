"""P4 잔여 — 환불 풀: 수수료 적립 + claim 판정 + 배상 (TDD).

제도적 신뢰 (2차 리서치 §1.3 보험 모델): 거래 수수료가 풀에 쌓이고,
나쁜 정보에 당한 구매자가 claim을 걸면 꼰대가 판정해 배상한다.
판정 입력(justified)은 grounding 결과/운영자 판단 — LLM 단독 심판 금지 원칙.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import duckdb
import pytest

from app.config import Settings
from app.credits.ledger import get_balance
from app.storage.invoices import insert_pending_invoice, mark_invoice_settled
from app.trust.refund_pool import (
    VILLAGE_POOL_AGENT_ID,
    ClaimError,
    accrue_pool_fee,
    adjudicate_claim,
    file_claim,
)

T0 = datetime(2026, 7, 13, 9, 0, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "db_path": ":memory:",
        "jaccard_window": 50,
        "jaccard_threshold": 0.9,
        "payment_enabled": True,
        "refund_pool_fee": 1,
        "query_price": 3,
        "starting_grant": 100,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _settled_invoice(conn: duckdb.DuckDBPyConnection) -> str:
    invoice_id = str(uuid.uuid4())
    insert_pending_invoice(
        conn,
        invoice_id=invoice_id,
        query="그 얘기 사실인가?",
        subject_agent="kimbot",
        intent_expiry=T0,
    )
    mark_invoice_settled(conn, invoice_id, str(uuid.uuid4()), settled_at=T0)
    return invoice_id


def test_accrue_pool_fee(tmp_db: duckdb.DuckDBPyConnection) -> None:
    settings = _settings()
    invoice_id = _settled_invoice(tmp_db)
    accrue_pool_fee(tmp_db, settings, invoice_id=invoice_id, now=T0)
    assert get_balance(tmp_db, VILLAGE_POOL_AGENT_ID) == settings.starting_grant + 1


def test_accrue_pool_fee_is_idempotent(tmp_db: duckdb.DuckDBPyConnection) -> None:
    """M4 회귀 — 같은 invoice로 두 번 적립해도 풀 잔고는 한 번만 늘어야 한다
    (재시도/중복 호출 방어)."""
    settings = _settings()
    invoice_id = _settled_invoice(tmp_db)
    accrue_pool_fee(tmp_db, settings, invoice_id=invoice_id, now=T0)
    accrue_pool_fee(tmp_db, settings, invoice_id=invoice_id, now=T0)  # 중복 호출
    assert (
        get_balance(tmp_db, VILLAGE_POOL_AGENT_ID)
        == settings.starting_grant + settings.refund_pool_fee
    )


def test_claim_approved_pays_refund(tmp_db: duckdb.DuckDBPyConnection) -> None:
    settings = _settings()
    invoice_id = _settled_invoice(tmp_db)
    accrue_pool_fee(tmp_db, settings, invoice_id=invoice_id, now=T0)
    claim_id = file_claim(
        tmp_db,
        claimant_agent="querier_zed",
        invoice_id=invoice_id,
        reason_text="산 narrative가 나중 사료와 모순",
        now=T0,
    )
    decision = adjudicate_claim(
        tmp_db, settings, claim_id=claim_id, justified=True, now=T0
    )
    assert decision.status == "approved"
    assert decision.payout == settings.query_price
    # 환불: pool → 구매자
    assert (
        get_balance(tmp_db, "querier_zed")
        == settings.starting_grant + settings.query_price
    )
    row = tmp_db.execute(
        "SELECT status, payout_tx_id FROM refund_claims WHERE claim_id = ?",
        [claim_id],
    ).fetchone()
    assert row is not None
    assert row[0] == "approved"
    assert row[1] is not None


def test_adjudicate_claim_guards_against_double_pay_on_race(
    tmp_db: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M3 회귀 — pre-check와 UPDATE 사이에 동시 판정이 끼어들어도 이중 배상이
    나면 안 된다. UPDATE가 status='pending' 가드로 레이스 패자를 거부해야 한다."""
    import app.trust.refund_pool as rp

    settings = _settings()
    invoice_id = _settled_invoice(tmp_db)
    accrue_pool_fee(tmp_db, settings, invoice_id=invoice_id, now=T0)
    claim_id = file_claim(
        tmp_db,
        claimant_agent="querier_zed",
        invoice_id=invoice_id,
        reason_text="모순",
        now=T0,
    )

    real_transfer = rp.credits_transfer

    def racing_transfer(conn: object, **kw: object) -> object:
        # 동시 판정이 먼저 승인한 상황 재현: 우리 UPDATE 직전에 status가 바뀜
        tmp_db.execute(
            "UPDATE refund_claims SET status='approved' WHERE claim_id = ?",
            [claim_id],
        )
        return real_transfer(conn, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(rp, "credits_transfer", racing_transfer)
    with pytest.raises(ClaimError):
        adjudicate_claim(
            tmp_db, settings, claim_id=claim_id, justified=True, now=T0
        )


def test_claim_denied_pays_nothing(tmp_db: duckdb.DuckDBPyConnection) -> None:
    settings = _settings()
    invoice_id = _settled_invoice(tmp_db)
    claim_id = file_claim(
        tmp_db,
        claimant_agent="querier_zed",
        invoice_id=invoice_id,
        reason_text="그냥 마음에 안 듦",
        now=T0,
    )
    decision = adjudicate_claim(
        tmp_db, settings, claim_id=claim_id, justified=False, now=T0
    )
    assert decision.status == "denied"
    assert decision.payout == 0
    assert get_balance(tmp_db, "querier_zed") == 0  # grant도 없음 (터치 안 함)


def test_claim_unknown_invoice_raises(tmp_db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ClaimError):
        file_claim(
            tmp_db,
            claimant_agent="querier_zed",
            invoice_id=str(uuid.uuid4()),
            reason_text="x",
            now=T0,
        )


def test_double_adjudication_raises(tmp_db: duckdb.DuckDBPyConnection) -> None:
    settings = _settings()
    invoice_id = _settled_invoice(tmp_db)
    accrue_pool_fee(tmp_db, settings, invoice_id=invoice_id, now=T0)
    claim_id = file_claim(
        tmp_db,
        claimant_agent="querier_zed",
        invoice_id=invoice_id,
        reason_text="모순",
        now=T0,
    )
    adjudicate_claim(tmp_db, settings, claim_id=claim_id, justified=True, now=T0)
    with pytest.raises(ClaimError):
        adjudicate_claim(
            tmp_db, settings, claim_id=claim_id, justified=True, now=T0
        )
