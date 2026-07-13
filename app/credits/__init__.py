"""Credits ledger (v1.5 alpha) — off-chain bidirectional payment.

Public API:

    from app.credits.ledger import (
        CreditsTransaction,
        InsufficientFundsError,
        InvalidAgentError,
        Ledger,
        get_balance,
        transfer,
    )

Callers must wrap ``transfer`` in their own DuckDB BEGIN/COMMIT/ROLLBACK
(same convention as ``app/storage/events.py``). v2.5 race-safety pattern.
"""
