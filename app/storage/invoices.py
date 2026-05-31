"""``invoices`` storage helpers — pay-to-query lifecycle (v1.5 alpha).

All helpers take a ``duckdb.DuckDBPyConnection`` (or cursor) and MUST NOT
manage their own transaction — callers wrap (same convention as
``app/storage/events.py``). Per PRD D5, invoice issuance and settlement
are separate TXs so settlement failure does not erase the audit row.

Lifecycle: pending -> settled | invalidated | expired.
"""

from __future__ import annotations

from datetime import datetime

import duckdb


def insert_pending_invoice(
    conn: duckdb.DuckDBPyConnection,
    *,
    invoice_id: str,
    query: str,
    subject_agent: str | None,
    intent_expiry: datetime,
) -> None:
    """Insert a fresh invoice with status='pending'. Caller commits."""
    conn.execute(
        "INSERT INTO invoices "
        "(invoice_id, query, subject_agent, intent_expiry, status) "
        "VALUES (?, ?, ?, ?, 'pending')",
        [invoice_id, query, subject_agent, intent_expiry],
    )


def mark_invoice_settled(
    conn: duckdb.DuckDBPyConnection,
    invoice_id: str,
    credits_tx_id: str,
    *,
    settled_at: datetime,
) -> None:
    """Transition invoice pending -> settled. Caller commits.

    No-op if the invoice was already in a terminal state - the
    ``WHERE status='pending'`` guard preserves race-safety per
    outside voice T7b (RETURNING-style ownership).
    """
    conn.execute(
        "UPDATE invoices "
        "SET status='settled', credits_tx_id=?, settled_at=? "
        "WHERE invoice_id=? AND status='pending'",
        [credits_tx_id, settled_at, invoice_id],
    )


def mark_invoice_invalidated(
    conn: duckdb.DuckDBPyConnection,
    invoice_id: str,
) -> None:
    """Transition invoice pending -> invalidated (e.g. payment refused).

    Race-safe via ``WHERE status='pending'`` guard.
    """
    conn.execute(
        "UPDATE invoices SET status='invalidated' "
        "WHERE invoice_id=? AND status='pending'",
        [invoice_id],
    )


def mark_expired_invoices(
    conn: duckdb.DuckDBPyConnection,
    *,
    now: datetime,
) -> int:
    """Sweep pending invoices whose intent_expiry has passed.

    Returns the count actually transitioned. Caller commits. Designed
    for an asyncio background task per PRD section 6 cleanup loop.
    """
    rows = conn.execute(
        "SELECT invoice_id FROM invoices "
        "WHERE status='pending' AND intent_expiry < ?",
        [now],
    ).fetchall()
    if not rows:
        return 0
    expired_ids = [r[0] for r in rows]
    placeholders = ",".join(["?"] * len(expired_ids))
    conn.execute(
        f"UPDATE invoices SET status='expired' "
        f"WHERE invoice_id IN ({placeholders}) AND status='pending'",
        expired_ids,
    )
    return len(expired_ids)


def get_invoice_status(
    conn: duckdb.DuckDBPyConnection,
    invoice_id: str,
) -> str | None:
    """Return current invoice status or None if not found."""
    row = conn.execute(
        "SELECT status FROM invoices WHERE invoice_id=?",
        [invoice_id],
    ).fetchone()
    return str(row[0]) if row else None
