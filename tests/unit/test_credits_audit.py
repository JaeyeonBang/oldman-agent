"""개선 A — credits 회계 감사: 자산 보존 invariant (TDD).

모든 transfer는 zero-sum이므로 Σ(잔고) == Σ(시스템 발행: starting_grant +
admin_adjust)이어야 한다. escrow 정합: paid escrow는 대응하는 royalty tx를
가져야 한다. 이 invariant가 깨지면 돈이 새거나 위조된 것.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import duckdb

from app.config import Settings
from app.credits.audit import audit_credits
from app.credits.ledger import transfer
from app.trust.payout import release_royalties_for_citations, split_publish_payment

T0 = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)


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


def test_empty_ledger_is_balanced(tmp_db: duckdb.DuckDBPyConnection) -> None:
    report = audit_credits(tmp_db)
    assert report.balanced is True
    assert report.total_balance == 0
    assert report.total_minted == 0


def test_transfers_preserve_assets(tmp_db: duckdb.DuckDBPyConnection) -> None:
    tmp_db.execute("BEGIN")
    transfer(
        tmp_db,
        from_agent="alice",
        to_agent="bob",
        amount=7,
        reason="query_price",
        starting_grant=100,
    )
    tmp_db.execute("COMMIT")
    report = audit_credits(tmp_db)
    assert report.balanced is True
    assert report.total_minted == 200  # grant 2건
    assert report.total_balance == 200


def test_full_payout_cycle_is_balanced(tmp_db: duckdb.DuckDBPyConnection) -> None:
    settings = _settings()
    event_id = str(uuid.uuid4())
    tmp_db.execute("BEGIN")
    split_publish_payment(
        tmp_db, settings, event_id=event_id, seller_agent="kimbot", now=T0
    )
    tmp_db.execute("COMMIT")
    release_royalties_for_citations(
        tmp_db,
        settings,
        citation_event_ids=[event_id],
        invoice_id=str(uuid.uuid4()),
        now=T0,
    )
    report = audit_credits(tmp_db)
    assert report.balanced is True
    assert report.issues == []
    assert report.open_escrow_liability == 0  # 전부 지급됨


def test_tampered_balance_is_detected(tmp_db: duckdb.DuckDBPyConnection) -> None:
    tmp_db.execute("BEGIN")
    transfer(
        tmp_db,
        from_agent="alice",
        to_agent="bob",
        amount=1,
        reason="query_price",
        starting_grant=100,
    )
    tmp_db.execute("COMMIT")
    # 위조: 잔고를 몰래 부풀림 (대응 tx 없음)
    tmp_db.execute(
        "UPDATE credits_balances SET balance = balance + 999 WHERE agent_id='bob'"
    )
    report = audit_credits(tmp_db)
    assert report.balanced is False
    assert any("mint" in i or "balance" in i for i in report.issues)


def test_paid_escrow_without_tx_is_flagged(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    settings = _settings()
    event_id = str(uuid.uuid4())
    tmp_db.execute("BEGIN")
    split_publish_payment(
        tmp_db, settings, event_id=event_id, seller_agent="kimbot", now=T0
    )
    tmp_db.execute("COMMIT")
    # 위조: royalty tx 없이 escrow만 paid로 조작
    tmp_db.execute(
        "UPDATE royalty_escrows SET status='paid', paid_tx_id=? WHERE event_id=?",
        [str(uuid.uuid4()), event_id],
    )
    report = audit_credits(tmp_db)
    assert any("escrow" in i for i in report.issues)
