"""credits 회계 감사 — 자산 보존 invariant + escrow 정합 (개선 A).

원리: 모든 transfer는 zero-sum이므로

    Σ(credits_balances.balance) == Σ(시스템 발행 tx amount)
    (발행 = from_agent IS NULL AND outcome='applied' — starting_grant/admin_adjust)

가 항상 성립해야 한다. 깨지면 잔고 위조/이중 지급/유실. escrow 정합:
status='paid'인 escrow는 대응하는 reason='royalty' tx(paid_tx_id)가
실존해야 한다. open escrow 총액은 미래 부채로 리포트.

읽기 전용 — village_demo/trust_sim 말미와 admin 점검에서 호출.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb


@dataclass(frozen=True)
class CreditsAudit:
    total_balance: int
    total_minted: int
    open_escrow_liability: int
    balanced: bool
    issues: list[str] = field(default_factory=list)


def _scalar(conn: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def audit_credits(conn: duckdb.DuckDBPyConnection) -> CreditsAudit:
    issues: list[str] = []

    total_balance = _scalar(
        conn, "SELECT COALESCE(SUM(balance), 0) FROM credits_balances"
    )
    total_minted = _scalar(
        conn,
        "SELECT COALESCE(SUM(amount), 0) FROM credits_transactions "
        "WHERE from_agent IS NULL AND outcome = 'applied'",
    )
    balanced = total_balance == total_minted
    if not balanced:
        issues.append(
            f"balance/mint mismatch: sum(balance)={total_balance} != "
            f"sum(minted)={total_minted} (diff={total_balance - total_minted})"
        )

    open_escrow_liability = _scalar(
        conn,
        "SELECT COALESCE(SUM(amount), 0) FROM royalty_escrows WHERE status='open'",
    )

    orphan_paid = conn.execute(
        "SELECT e.event_id FROM royalty_escrows e "
        "LEFT JOIN credits_transactions t "
        "  ON t.tx_id = TRY_CAST(e.paid_tx_id AS UUID) AND t.reason = 'royalty' "
        "WHERE e.status = 'paid' AND t.tx_id IS NULL"
    ).fetchall()
    for (event_id,) in orphan_paid:
        issues.append(f"paid escrow without royalty tx: event_id={event_id}")

    return CreditsAudit(
        total_balance=total_balance,
        total_minted=total_minted,
        open_escrow_liability=open_escrow_liability,
        balanced=balanced,
        issues=issues,
    )
