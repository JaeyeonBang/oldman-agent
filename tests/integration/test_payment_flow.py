"""v1.5 alpha T3 — payment integration tests (G2/G3/G4/G5).

G2: payment_enabled + funded oldman + publish -> events.credits_tx_id set,
    credits applied.
G3: payment_enabled + oldman 0-balance + publish -> OldmanInsufficientFundsError
    raised, 0 rows in events, audit row absent (rolled back) but contract
    consistent.
G4: payment_enabled + funded querier + query -> invoice settled, narrative
    returned.
G5: payment_enabled + unfunded querier + query -> invoice invalidated,
    fallback artifact emitted.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import duckdb
import pytest

from app.api.publish import (
    OLDMAN_TREASURY_AGENT_ID,
    OldmanInsufficientFundsError,
    execute_publish,
)
from app.api.schemas import PublishRequest
from app.config import Settings
from app.credits.ledger import DEFAULT_STARTING_GRANT, get_balance


def _payment_settings(**overrides: Any) -> Settings:
    """Settings with payment_enabled=True. Override per test."""
    defaults: dict[str, Any] = {
        "db_path": ":memory:",
        "jaccard_window": 50,
        "jaccard_threshold": 0.9,
        "payment_enabled": True,
        "publish_reward": 1,
        "query_price": 1,
        "starting_grant": DEFAULT_STARTING_GRANT,
        "invoice_ttl_seconds": 300,
        "payment_kill_switch": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


# ── G2 / G3 — publish path ──────────────────────────────────────────────────


class TestG2PublishPaymentApplied:
    @pytest.mark.asyncio
    async def test_publish_with_payment_enabled_populates_credits_tx_id(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        req = PublishRequest(
            event_kind="chat",
            source_agent="agent_alice",
            declared_source_type="self",
            payload={"text": "hello world"},
        )
        resp = await execute_publish(tmp_db, _payment_settings(), req)
        assert resp.status == "stored"

        row = tmp_db.execute(
            "SELECT credits_tx_id FROM events WHERE event_id = ?",
            [resp.event_id],
        ).fetchone()
        assert row is not None and row[0] is not None
        credits_tx_id = row[0]

        tx_row = tmp_db.execute(
            "SELECT from_agent, to_agent, amount, reason, outcome, event_id "
            "FROM credits_transactions WHERE tx_id = ?",
            [credits_tx_id],
        ).fetchone()
        assert tx_row is not None
        from_agent, to_agent, amount, reason, outcome, event_id = tx_row
        assert from_agent == OLDMAN_TREASURY_AGENT_ID
        assert to_agent == "agent_alice"
        assert amount == 1
        assert reason == "publish_reward"
        assert outcome == "applied"
        assert str(event_id) == resp.event_id

        assert get_balance(tmp_db, OLDMAN_TREASURY_AGENT_ID) == DEFAULT_STARTING_GRANT - 1
        assert get_balance(tmp_db, "agent_alice") == DEFAULT_STARTING_GRANT + 1


class TestG3PublishPaymentInsufficientRollsBack:
    @pytest.mark.asyncio
    async def test_oldman_zero_balance_rolls_back_event_and_raises(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        tmp_db.execute(
            "INSERT INTO credits_balances (agent_id, balance, last_updated) "
            "VALUES (?, 0, CURRENT_TIMESTAMP)",
            [OLDMAN_TREASURY_AGENT_ID],
        )

        req = PublishRequest(
            event_kind="chat",
            source_agent="agent_alice",
            declared_source_type="self",
            payload={"text": "broke"},
        )

        with pytest.raises(OldmanInsufficientFundsError):
            await execute_publish(tmp_db, _payment_settings(), req)

        events_count = tmp_db.execute(
            "SELECT count(*) FROM events"
        ).fetchone()
        assert events_count is not None and events_count[0] == 0

        applied_count = tmp_db.execute(
            "SELECT count(*) FROM credits_transactions WHERE outcome='applied'"
        ).fetchone()
        assert applied_count is not None and applied_count[0] == 0

        assert get_balance(tmp_db, OLDMAN_TREASURY_AGENT_ID) == 0


class TestG3BackwardCompatNoPayment:
    @pytest.mark.asyncio
    async def test_publish_with_payment_disabled_does_not_touch_ledger(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        """G6 cousin: payment_enabled=False keeps ledger empty."""
        req = PublishRequest(
            event_kind="chat",
            source_agent="agent_alice",
            declared_source_type="self",
            payload={"text": "free path"},
        )
        settings = _payment_settings(payment_enabled=False)
        resp = await execute_publish(tmp_db, settings, req)
        assert resp.status == "stored"

        row = tmp_db.execute(
            "SELECT credits_tx_id FROM events WHERE event_id = ?",
            [resp.event_id],
        ).fetchone()
        assert row is not None and row[0] is None

        tx_count = tmp_db.execute(
            "SELECT count(*) FROM credits_transactions"
        ).fetchone()
        assert tx_count is not None and tx_count[0] == 0


class TestKillSwitchSkipsLedger:
    @pytest.mark.asyncio
    async def test_kill_switch_active_bypasses_payment(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        """PRD D8 / outside voice T7c: kill-switch tripped means free path
        even when payment_enabled is true."""
        req = PublishRequest(
            event_kind="chat",
            source_agent="agent_alice",
            declared_source_type="self",
            payload={"text": "emergency exit"},
        )
        settings = _payment_settings(payment_kill_switch=True)
        resp = await execute_publish(tmp_db, settings, req)
        assert resp.status == "stored"

        row = tmp_db.execute(
            "SELECT credits_tx_id FROM events WHERE event_id = ?",
            [resp.event_id],
        ).fetchone()
        assert row is not None and row[0] is None

        tx_count = tmp_db.execute(
            "SELECT count(*) FROM credits_transactions"
        ).fetchone()
        assert tx_count is not None and tx_count[0] == 0


# ── G4 / G5 — query path via OldmanAgentExecutor ───────────────────────────


def _seed_event_for_query(
    conn: duckdb.DuckDBPyConnection,
    *,
    subject_agent: str = "agent_alice",
) -> str:
    """Seed a single event so cold-start fallback isn't triggered."""
    eid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO events "
        "(event_id, ts, kind, source_agent, source_type, "
        " payload_json, payload_hash) "
        "VALUES (?, NOW(), 'chat', ?, 'self', ?, ?)",
        [eid, subject_agent, json.dumps({"text": "seed"}), eid[:32]],
    )
    return eid


class _CapturingQueue:
    """Minimal EventQueue stub capturing emitted events for inspection."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)

    async def close(self) -> None:
        return None

    def is_closed(self) -> bool:
        return False


class TestG4QueryPaymentSettles:
    """Direct test of `_charge_querier_or_fallback` — isolates payment
    logic from the LLM provider so G4 doesn't require a narrative mock."""

    @pytest.mark.asyncio
    async def test_funded_querier_settles_invoice(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.a2a.executor import OldmanAgentExecutor

        executor = OldmanAgentExecutor(
            conn=tmp_db,
            settings=_payment_settings(),
            narrative_provider=None,
            reflection_provider=None,
            judge_provider=None,
        )
        queue = _CapturingQueue()
        handled = await executor._charge_querier_or_fallback(
            question="agent_alice가 무엇을 했나요?",
            subject_agent="agent_alice",
            querier_agent="querier_zed",
            task_id="task-1",
            context_id="ctx-1",
            event_queue=queue,
        )
        assert handled is False

        rows = tmp_db.execute(
            "SELECT status, credits_tx_id, settled_at FROM invoices"
        ).fetchall()
        assert len(rows) == 1
        status, credits_tx_id, settled_at = rows[0]
        assert status == "settled"
        assert credits_tx_id is not None
        assert settled_at is not None

        assert get_balance(tmp_db, "querier_zed") == DEFAULT_STARTING_GRANT - 1
        assert get_balance(tmp_db, OLDMAN_TREASURY_AGENT_ID) == DEFAULT_STARTING_GRANT + 1

        assert queue.events == []


class TestG5QueryPaymentInvalidated:
    @pytest.mark.asyncio
    async def test_unfunded_querier_invalidates_invoice_and_emits_fallback(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.a2a.executor import OldmanAgentExecutor

        tmp_db.execute(
            "INSERT INTO credits_balances (agent_id, balance, last_updated) "
            "VALUES ('querier_broke', 0, CURRENT_TIMESTAMP)"
        )

        executor = OldmanAgentExecutor(
            conn=tmp_db,
            settings=_payment_settings(),
            narrative_provider=None,
            reflection_provider=None,
            judge_provider=None,
        )
        queue = _CapturingQueue()
        handled = await executor._charge_querier_or_fallback(
            question="알려줘",
            subject_agent="agent_alice",
            querier_agent="querier_broke",
            task_id="task-2",
            context_id="ctx-2",
            event_queue=queue,
        )
        assert handled is True

        rows = tmp_db.execute(
            "SELECT status FROM invoices"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "invalidated"

        assert get_balance(tmp_db, "querier_broke") == 0

        assert len(queue.events) == 2

    @pytest.mark.asyncio
    async def test_missing_querier_agent_emits_fallback_without_invoice(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.a2a.executor import OldmanAgentExecutor

        executor = OldmanAgentExecutor(
            conn=tmp_db,
            settings=_payment_settings(),
            narrative_provider=None,
            reflection_provider=None,
            judge_provider=None,
        )
        queue = _CapturingQueue()
        handled = await executor._charge_querier_or_fallback(
            question="who?",
            subject_agent=None,
            querier_agent=None,
            task_id="task-3",
            context_id="ctx-3",
            event_queue=queue,
        )
        assert handled is True

        invoices_count = tmp_db.execute(
            "SELECT count(*) FROM invoices"
        ).fetchone()
        assert invoices_count is not None and invoices_count[0] == 0

        assert len(queue.events) == 2
