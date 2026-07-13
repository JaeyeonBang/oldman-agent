"""v1.5 alpha T2 — Ledger.transfer + lazy starting-grant unit tests.

Covers G1 acceptance gate from `.claude/prds/oldman-agent-v1_5.prd.md`:
success, insufficient_funds, invalid_agent, double-counted, v2.5 T4 regression.
"""

from __future__ import annotations

import asyncio
import uuid

import duckdb
import pytest

from app.credits.ledger import (
    DEFAULT_STARTING_GRANT,
    InsufficientFundsError,
    InvalidAgentError,
    Ledger,
    get_balance,
    transfer,
)


class TestLedgerSuccess:
    def test_publish_reward_oldman_to_source_agent_applies(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        tx = transfer(
            tmp_db,
            from_agent="oldman",
            to_agent="agent_alice",
            amount=1,
            reason="publish_reward",
            event_id=str(uuid.uuid4()),
        )
        assert tx.outcome == "applied"
        assert get_balance(tmp_db, "oldman") == DEFAULT_STARTING_GRANT - 1
        assert get_balance(tmp_db, "agent_alice") == DEFAULT_STARTING_GRANT + 1

        rows = tmp_db.execute(
            "SELECT reason, outcome FROM credits_transactions ORDER BY ts"
        ).fetchall()
        reasons = [r[0] for r in rows]
        outcomes = [r[1] for r in rows]
        assert reasons.count("starting_grant") == 2
        assert reasons.count("publish_reward") == 1
        assert outcomes == ["applied", "applied", "applied"]

    def test_query_price_querier_to_oldman_applies(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        tx = transfer(
            tmp_db,
            from_agent="querier_zed",
            to_agent="oldman",
            amount=1,
            reason="query_price",
            invoice_id=str(uuid.uuid4()),
        )
        assert tx.outcome == "applied"
        assert get_balance(tmp_db, "querier_zed") == DEFAULT_STARTING_GRANT - 1
        assert get_balance(tmp_db, "oldman") == DEFAULT_STARTING_GRANT + 1


class TestLedgerInsufficientFunds:
    def test_zero_balance_agent_pays_raises_and_records_rejection(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        tmp_db.execute(
            "INSERT INTO credits_balances (agent_id, balance, last_updated) "
            "VALUES ('agent_alice', 0, CURRENT_TIMESTAMP)"
        )

        with pytest.raises(InsufficientFundsError) as exc_info:
            transfer(
                tmp_db,
                from_agent="agent_alice",
                to_agent="oldman",
                amount=1,
                reason="query_price",
            )

        assert exc_info.value.agent_id == "agent_alice"
        assert exc_info.value.balance == 0
        assert exc_info.value.required == 1

        assert get_balance(tmp_db, "agent_alice") == 0
        assert get_balance(tmp_db, "oldman") == DEFAULT_STARTING_GRANT

        rej = tmp_db.execute(
            "SELECT outcome FROM credits_transactions "
            "WHERE outcome = 'rejected_insufficient_funds'"
        ).fetchall()
        assert len(rej) == 1


class TestLedgerInvalidAgent:
    def test_amount_zero_raises_invalid(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        with pytest.raises(InvalidAgentError):
            transfer(
                tmp_db,
                from_agent="agent_alice",
                to_agent="oldman",
                amount=0,
                reason="query_price",
            )

    def test_publish_reward_with_missing_from_agent_raises(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        with pytest.raises(InvalidAgentError):
            transfer(
                tmp_db,
                from_agent=None,
                to_agent="agent_alice",
                amount=1,
                reason="publish_reward",
            )

    def test_empty_string_agent_id_raises(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        with pytest.raises(InvalidAgentError):
            transfer(
                tmp_db,
                from_agent="",
                to_agent="agent_alice",
                amount=1,
                reason="publish_reward",
            )


class TestLedgerDoubleCounted:
    def test_three_transfers_produce_three_distinct_rows_and_correct_balance(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        for _ in range(3):
            transfer(
                tmp_db,
                from_agent="oldman",
                to_agent="agent_alice",
                amount=2,
                reason="publish_reward",
            )

        assert get_balance(tmp_db, "oldman") == DEFAULT_STARTING_GRANT - 6
        assert get_balance(tmp_db, "agent_alice") == DEFAULT_STARTING_GRANT + 6

        applied = tmp_db.execute(
            "SELECT count(*) FROM credits_transactions "
            "WHERE outcome='applied' AND reason='publish_reward'"
        ).fetchone()
        assert applied is not None and applied[0] == 3


class TestLedgerConcurrencyRegression:
    """v2.5 T4 race-safety pattern at credit layer.

    asyncio.gather of two transfers — single-writer DuckDB serializes
    them per-call atomically. Final balances must reflect both transfers
    completely (no lost update, no double-debit). Mirrors
    tests/unit/test_adversarial_v102.py::test_concurrent_same_hash_publish_*.
    """

    @pytest.mark.asyncio
    async def test_concurrent_transfers_preserve_double_entry_invariant(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        async def do_transfer() -> None:
            transfer(
                tmp_db,
                from_agent="oldman",
                to_agent="agent_alice",
                amount=1,
                reason="publish_reward",
            )

        await asyncio.gather(do_transfer(), do_transfer())

        assert get_balance(tmp_db, "oldman") == DEFAULT_STARTING_GRANT - 2
        assert get_balance(tmp_db, "agent_alice") == DEFAULT_STARTING_GRANT + 2

        applied = tmp_db.execute(
            "SELECT count(*) FROM credits_transactions "
            "WHERE outcome='applied' AND reason='publish_reward'"
        ).fetchone()
        assert applied is not None and applied[0] == 2


class TestLedgerConvenienceWrapper:
    def test_ledger_class_delegates_to_module_functions(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        Ledger.transfer(
            tmp_db,
            from_agent="oldman",
            to_agent="agent_alice",
            amount=1,
            reason="publish_reward",
        )
        assert Ledger.get_balance(tmp_db, "oldman") == DEFAULT_STARTING_GRANT - 1
