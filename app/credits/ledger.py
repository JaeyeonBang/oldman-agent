"""Credits ledger primitives — atomic transfer + lazy starting-grant.

::

    Ledger pipeline (called inside a caller-owned BEGIN/COMMIT/ROLLBACK):

      transfer(from_agent, to_agent, amount, reason, *, event_id, invoice_id)
        │
        ├─▶ validate amount > 0, reason ∈ enum, agents non-empty
        │     │
        │     └─▶ InvalidAgentError / ValueError (no row written)
        │
        ├─▶ _ensure_balance(from_agent)   ← lazy starting_grant if first touch
        ├─▶ _ensure_balance(to_agent)     ← lazy starting_grant if first touch
        │
        ├─▶ if from_agent balance < amount:
        │     INSERT credits_transactions (outcome='rejected_insufficient_funds')
        │     raise InsufficientFundsError
        │
        ├─▶ UPDATE credits_balances SET balance = balance - amount WHERE agent_id = from_agent
        ├─▶ UPDATE credits_balances SET balance = balance + amount WHERE agent_id = to_agent
        └─▶ INSERT credits_transactions (outcome='applied')
              │
              └─▶ return CreditsTransaction

    Lazy starting-grant (apply on first _ensure_balance call):
      from_agent = NULL  →  INSERT row with balance = starting_grant
                            + INSERT tx (reason='starting_grant', outcome='applied')

    System mints (from_agent=NULL) bypass balance check — only allowed for
    reason='starting_grant' and 'admin_adjust'. publish_reward / query_price
    always require both agents.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import duckdb

DEFAULT_STARTING_GRANT: Final[int] = 100

_REASONS_REQUIRE_BOTH_AGENTS: Final[frozenset[str]] = frozenset(
    {"publish_reward", "query_price"}
)
_REASONS_ALLOW_SYSTEM_FROM: Final[frozenset[str]] = frozenset(
    {"starting_grant", "admin_adjust"}
)


class LedgerError(Exception):
    """Base for ledger domain errors."""


class InsufficientFundsError(LedgerError):
    def __init__(self, agent_id: str, balance: int, required: int) -> None:
        super().__init__(
            f"agent={agent_id!r} balance={balance} < required={required}"
        )
        self.agent_id = agent_id
        self.balance = balance
        self.required = required


class InvalidAgentError(LedgerError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)


@dataclass(frozen=True)
class CreditsTransaction:
    tx_id: str
    ts: datetime
    from_agent: str | None
    to_agent: str | None
    amount: int
    reason: str
    event_id: str | None
    invoice_id: str | None
    outcome: str


def get_balance(conn: duckdb.DuckDBPyConnection, agent_id: str) -> int:
    """Return ``agent_id``'s balance, or 0 if no row yet (not granted)."""
    row = conn.execute(
        "SELECT balance FROM credits_balances WHERE agent_id = ?",
        [agent_id],
    ).fetchone()
    return int(row[0]) if row else 0


def _ensure_balance(
    conn: duckdb.DuckDBPyConnection,
    agent_id: str,
    starting_grant: int,
) -> int:
    """UPSERT credits_balances row; apply starting_grant on first touch.

    Returns the current balance. Caller must be inside a TX.
    """
    row = conn.execute(
        "SELECT balance FROM credits_balances WHERE agent_id = ?",
        [agent_id],
    ).fetchone()
    if row is not None:
        return int(row[0])
    conn.execute(
        "INSERT INTO credits_balances (agent_id, balance, last_updated) "
        "VALUES (?, ?, ?)",
        [agent_id, starting_grant, datetime.now(UTC)],
    )
    conn.execute(
        "INSERT INTO credits_transactions "
        "(tx_id, ts, from_agent, to_agent, amount, reason, "
        " event_id, invoice_id, outcome) "
        "VALUES (?, ?, NULL, ?, ?, 'starting_grant', NULL, NULL, 'applied')",
        [str(uuid.uuid4()), datetime.now(UTC), agent_id, starting_grant],
    )
    return starting_grant


def transfer(
    conn: duckdb.DuckDBPyConnection,
    *,
    from_agent: str | None,
    to_agent: str | None,
    amount: int,
    reason: str,
    event_id: str | None = None,
    invoice_id: str | None = None,
    starting_grant: int = DEFAULT_STARTING_GRANT,
) -> CreditsTransaction:
    """Atomic credits transfer; raises on insufficient funds or invalid args.

    Caller wraps in BEGIN/COMMIT/ROLLBACK. The rejected-insufficient_funds
    record is intentionally written inside the caller's TX — on ROLLBACK
    that row disappears too, leaving the ledger consistent. Callers that
    want the rejection to be visible (audit / metric) should commit the
    rejection in a separate TX before re-raising.
    """
    if amount <= 0:
        raise InvalidAgentError(f"amount must be > 0, got {amount}")
    if reason in _REASONS_REQUIRE_BOTH_AGENTS and (not from_agent or not to_agent):
        raise InvalidAgentError(
            f"reason={reason!r} requires both from_agent and to_agent"
        )
    if from_agent is None and reason not in _REASONS_ALLOW_SYSTEM_FROM:
        raise InvalidAgentError(
            f"reason={reason!r} cannot have system from_agent (NULL)"
        )
    if from_agent == "" or to_agent == "":
        raise InvalidAgentError("agent id must be non-empty string")

    now = datetime.now(UTC)
    tx_id = str(uuid.uuid4())

    from_balance: int | None = None
    if from_agent is not None:
        from_balance = _ensure_balance(conn, from_agent, starting_grant)
    if to_agent is not None:
        _ensure_balance(conn, to_agent, starting_grant)

    if from_balance is not None and from_balance < amount:
        # from_balance non-None implies from_agent non-None (set together above).
        assert from_agent is not None
        conn.execute(
            "INSERT INTO credits_transactions "
            "(tx_id, ts, from_agent, to_agent, amount, reason, "
            " event_id, invoice_id, outcome) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'rejected_insufficient_funds')",
            [tx_id, now, from_agent, to_agent, amount, reason, event_id, invoice_id],
        )
        raise InsufficientFundsError(from_agent, from_balance, amount)

    if from_agent is not None:
        conn.execute(
            "UPDATE credits_balances SET balance = balance - ?, "
            "last_updated = ? WHERE agent_id = ?",
            [amount, now, from_agent],
        )
    if to_agent is not None:
        conn.execute(
            "UPDATE credits_balances SET balance = balance + ?, "
            "last_updated = ? WHERE agent_id = ?",
            [amount, now, to_agent],
        )

    conn.execute(
        "INSERT INTO credits_transactions "
        "(tx_id, ts, from_agent, to_agent, amount, reason, "
        " event_id, invoice_id, outcome) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'applied')",
        [tx_id, now, from_agent, to_agent, amount, reason, event_id, invoice_id],
    )

    return CreditsTransaction(
        tx_id=tx_id,
        ts=now,
        from_agent=from_agent,
        to_agent=to_agent,
        amount=amount,
        reason=reason,
        event_id=event_id,
        invoice_id=invoice_id,
        outcome="applied",
    )


class Ledger:
    """Thin convenience wrapper. Stateless — methods just delegate."""

    @staticmethod
    def transfer(
        conn: duckdb.DuckDBPyConnection,
        *,
        from_agent: str | None,
        to_agent: str | None,
        amount: int,
        reason: str,
        event_id: str | None = None,
        invoice_id: str | None = None,
        starting_grant: int = DEFAULT_STARTING_GRANT,
    ) -> CreditsTransaction:
        return transfer(
            conn,
            from_agent=from_agent,
            to_agent=to_agent,
            amount=amount,
            reason=reason,
            event_id=event_id,
            invoice_id=invoice_id,
            starting_grant=starting_grant,
        )

    @staticmethod
    def get_balance(conn: duckdb.DuckDBPyConnection, agent_id: str) -> int:
        return get_balance(conn, agent_id)
