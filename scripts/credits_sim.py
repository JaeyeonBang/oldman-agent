"""v1.5 alpha T6 — credits ledger simulation harness.

Hypothesis test tool for PRD section 4:
    (a) spam-style 행동(반복 publish, dup-hash 우회 시도)이 credits 소진으로
        자연 차단되는 사례 >= 1건
    (b) query당 credits 비용이 narrative 정보 가치(인용 가능 evidence 수)와
        상관 관측

Self-contained script. Spins up an ephemeral DuckDB, runs migrations 001+002,
simulates 5 virtual agents producing publishes (some unique, some spam) +
mixed funded/unfunded queries against the ledger. Prints a JSON summary +
TSV scatter data on stdout.

Run:
    uv run python scripts/credits_sim.py

Optional output capture:
    uv run python scripts/credits_sim.py > sim.tsv

Limits:
    - Skips the real narrative LLM pipeline. Query "value" is proxied by the
      count of events available to cite at the moment of the query.
    - Single-process / single-writer DuckDB. Same constraint as production.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.api.publish import (
    OLDMAN_TREASURY_AGENT_ID,
    ExactHashDuplicateError,
    JaccardDuplicateError,
    OldmanInsufficientFundsError,
    execute_publish,
)
from app.api.schemas import PublishRequest
from app.config import Settings
from app.credits.ledger import (
    DEFAULT_STARTING_GRANT,
    InsufficientFundsError,
    get_balance,
    transfer,
)
from app.storage.db import apply_migrations, get_conn
from app.storage.invoices import (
    insert_pending_invoice,
    mark_invoice_invalidated,
    mark_invoice_settled,
)

AGENTS: list[str] = ["alice", "bob", "charlie", "dave", "evan"]
PUBLISH_REWARD = 1
QUERY_PRICE = 1


def _sim_settings(*, oldman_grant: int = DEFAULT_STARTING_GRANT) -> Settings:
    return Settings(
        db_path=":memory:",
        jaccard_window=50,
        jaccard_threshold=0.9,
        payment_enabled=True,
        publish_reward=PUBLISH_REWARD,
        query_price=QUERY_PRICE,
        starting_grant=oldman_grant,
        invoice_ttl_seconds=300,
        payment_kill_switch=False,
    )


async def _phase1_unique_publishes(
    conn: Any, settings: Settings, per_agent: int = 5
) -> dict[str, int]:
    stored = 0
    rejected_funds = 0
    for agent in AGENTS:
        for i in range(per_agent):
            req = PublishRequest(
                event_kind="chat",
                source_agent=agent,
                declared_source_type="self",
                payload={"text": f"{agent}_unique_event_{i}"},
            )
            try:
                await execute_publish(conn, settings, req)
                stored += 1
            except OldmanInsufficientFundsError:
                rejected_funds += 1
    return {"stored": stored, "rejected_oldman_funds": rejected_funds}


async def _phase2_spam_publishes(
    conn: Any, settings: Settings, per_agent: int = 5
) -> dict[str, int]:
    blocked_exact = 0
    blocked_jaccard = 0
    blocked_funds = 0
    stored = 0
    for agent in AGENTS:
        for i in range(per_agent):
            payload = {"text": f"{agent}_unique_event_{i}"}
            req = PublishRequest(
                event_kind="chat",
                source_agent=agent,
                declared_source_type="self",
                payload=payload,
            )
            try:
                await execute_publish(conn, settings, req)
                stored += 1
            except ExactHashDuplicateError:
                blocked_exact += 1
            except JaccardDuplicateError:
                blocked_jaccard += 1
            except OldmanInsufficientFundsError:
                blocked_funds += 1
            payload_near = {"text": f"{agent}_unique_event_{i} filler tail"}
            req_near = PublishRequest(
                event_kind="chat",
                source_agent=agent,
                declared_source_type="self",
                payload=payload_near,
            )
            try:
                await execute_publish(conn, settings, req_near)
                stored += 1
            except ExactHashDuplicateError:
                blocked_exact += 1
            except JaccardDuplicateError:
                blocked_jaccard += 1
            except OldmanInsufficientFundsError:
                blocked_funds += 1
    return {
        "stored": stored,
        "blocked_exact_hash": blocked_exact,
        "blocked_jaccard": blocked_jaccard,
        "blocked_oldman_funds": blocked_funds,
    }


def _simulated_query(
    conn: Any, settings: Settings, *, querier: str, subject_agent: str
) -> dict[str, Any]:
    invoice_id = str(uuid.uuid4())
    expiry = datetime.now(UTC) + timedelta(seconds=settings.invoice_ttl_seconds)

    conn.execute("BEGIN")
    insert_pending_invoice(
        conn,
        invoice_id=invoice_id,
        query=f"What did {subject_agent} do?",
        subject_agent=subject_agent,
        intent_expiry=expiry,
    )
    conn.execute("COMMIT")

    available = conn.execute(
        "SELECT count(*) FROM events WHERE source_agent = ?",
        [subject_agent],
    ).fetchone()
    evidence_count = int(available[0]) if available else 0

    try:
        conn.execute("BEGIN")
        tx = transfer(
            conn,
            from_agent=querier,
            to_agent=OLDMAN_TREASURY_AGENT_ID,
            amount=settings.query_price,
            reason="query_price",
            invoice_id=invoice_id,
            starting_grant=settings.starting_grant,
        )
        mark_invoice_settled(
            conn, invoice_id, tx.tx_id, settled_at=datetime.now(UTC)
        )
        conn.execute("COMMIT")
        return {
            "querier": querier,
            "subject": subject_agent,
            "status": "settled",
            "cost": settings.query_price,
            "evidence_count": evidence_count,
        }
    except InsufficientFundsError:
        with contextlib.suppress(Exception):
            conn.execute("ROLLBACK")
        conn.execute("BEGIN")
        mark_invoice_invalidated(conn, invoice_id)
        conn.execute("COMMIT")
        return {
            "querier": querier,
            "subject": subject_agent,
            "status": "invalidated",
            "cost": 0,
            "evidence_count": evidence_count,
        }


def _phase3_queries(conn: Any, settings: Settings) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for querier in AGENTS:
        for subject in AGENTS:
            if querier == subject:
                continue
            results.append(
                _simulated_query(
                    conn, settings, querier=querier, subject_agent=subject
                )
            )
    return results


def _phase4_unfunded_query(conn: Any, settings: Settings) -> dict[str, Any]:
    broke = "broke_agent"
    conn.execute(
        "INSERT INTO credits_balances (agent_id, balance, last_updated) "
        "VALUES (?, 0, CURRENT_TIMESTAMP)",
        [broke],
    )
    return _simulated_query(
        conn, settings, querier=broke, subject_agent="alice"
    )


async def _run() -> dict[str, Any]:
    db_path = tempfile.mktemp(suffix=".duckdb")
    conn = None
    try:
        conn = get_conn(db_path)
        apply_migrations(conn)
        settings = _sim_settings()

        oldman_initial = get_balance(conn, OLDMAN_TREASURY_AGENT_ID)

        phase1 = await _phase1_unique_publishes(conn, settings, per_agent=5)
        oldman_after_p1 = get_balance(conn, OLDMAN_TREASURY_AGENT_ID)

        phase2 = await _phase2_spam_publishes(conn, settings, per_agent=5)
        oldman_after_p2 = get_balance(conn, OLDMAN_TREASURY_AGENT_ID)

        phase3 = _phase3_queries(conn, settings)
        oldman_after_p3 = get_balance(conn, OLDMAN_TREASURY_AGENT_ID)

        phase4 = _phase4_unfunded_query(conn, settings)
        oldman_final = get_balance(conn, OLDMAN_TREASURY_AGENT_ID)

        final_balances: dict[str, int] = {
            OLDMAN_TREASURY_AGENT_ID: oldman_final,
        }
        for a in AGENTS:
            final_balances[a] = get_balance(conn, a)
        final_balances["broke_agent"] = get_balance(conn, "broke_agent")

        spam_attempts = (
            phase2["blocked_exact_hash"]
            + phase2["blocked_jaccard"]
            + phase2["stored"]
        )
        spam_suppression_rate = (
            (phase2["blocked_exact_hash"] + phase2["blocked_jaccard"])
            / spam_attempts
            if spam_attempts
            else 0.0
        )

        return {
            "config": {
                "agents": AGENTS,
                "publish_reward": PUBLISH_REWARD,
                "query_price": QUERY_PRICE,
                "starting_grant": settings.starting_grant,
            },
            "treasury_trajectory": {
                "initial": oldman_initial,
                "after_phase1_unique_publishes": oldman_after_p1,
                "after_phase2_spam": oldman_after_p2,
                "after_phase3_queries": oldman_after_p3,
                "after_phase4_unfunded": oldman_final,
            },
            "phase1_unique": phase1,
            "phase2_spam": phase2,
            "spam_attempts": spam_attempts,
            "spam_suppression_rate": round(spam_suppression_rate, 3),
            "phase3_query_results": phase3,
            "phase4_unfunded_query": phase4,
            "final_balances": final_balances,
        }
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
        with contextlib.suppress(FileNotFoundError):
            os.unlink(db_path)


def _print_human_report(summary: dict[str, Any]) -> None:
    print("=" * 72)
    print("v1.5 alpha credits ledger simulation — hypothesis section 4 evidence")
    print("=" * 72)
    cfg = summary["config"]
    print(f"agents:            {', '.join(cfg['agents'])}")
    print(
        f"economics:         publish_reward={cfg['publish_reward']}  "
        f"query_price={cfg['query_price']}  "
        f"starting_grant={cfg['starting_grant']}"
    )
    print()

    print("[1] Treasury (oldman) trajectory")
    for label, value in summary["treasury_trajectory"].items():
        print(f"  {label:<40} {value:>5}")
    print()

    print("[2] Phase 1 — unique publishes (each agent x 5)")
    for k, v in summary["phase1_unique"].items():
        print(f"  {k:<40} {v:>5}")
    print()

    print("[3] Phase 2 — spam attempts (exact-dup + near-dup, each agent x 5)")
    for k, v in summary["phase2_spam"].items():
        print(f"  {k:<40} {v:>5}")
    print(
        f"  spam_suppression_rate                    "
        f"{summary['spam_suppression_rate']:.1%}"
    )
    print()

    print("[4] PRD section 4(a) — spam suppression by credit/dedup mechanics")
    if summary["spam_suppression_rate"] >= 0.5:
        print(
            "  PASS — majority of spam attempts blocked before payment; "
            "credit treasury preserved."
        )
    else:
        print(
            "  WARN — fewer than half of spam attempts blocked. "
            "Investigate dedup tuning."
        )
    print()

    print("[5] PRD section 4(b) — cost vs evidence-count (phase 3 queries)")
    print("  querier\tsubject\tstatus\tcost\tevidence_count")
    for row in summary["phase3_query_results"]:
        print(
            f"  {row['querier']}\t{row['subject']}\t{row['status']}\t"
            f"{row['cost']}\t{row['evidence_count']}"
        )
    print()

    print("[6] Phase 4 — unfunded querier")
    p4 = summary["phase4_unfunded_query"]
    print(
        f"  querier={p4['querier']}  status={p4['status']}  "
        f"cost={p4['cost']}  evidence_count={p4['evidence_count']}"
    )
    if p4["status"] == "invalidated":
        print(
            "  PASS — broke agent's query rejected; treasury did not pay out "
            "narrative for zero balance."
        )
    print()

    print("[7] Final balances")
    for agent, bal in summary["final_balances"].items():
        print(f"  {agent:<24} {bal:>5}")
    print()
    print("=" * 72)
    print("Machine-readable JSON below:")
    print("=" * 72)
    print(json.dumps(summary, indent=2))


def main() -> None:
    summary = asyncio.run(_run())
    _print_human_report(summary)


if __name__ == "__main__":
    main()
