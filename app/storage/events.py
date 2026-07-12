"""``events`` L0 storage helpers.

All helpers take a ``duckdb.DuckDBPyConnection`` (or cursor) and MUST NOT
manage their own transaction — Phase 1.4 publish handler wraps the full
insert pipeline in a single BEGIN/COMMIT/ROLLBACK (T2).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import duckdb


def insert_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    event_id: str,
    ts: datetime,
    kind: str,
    source_agent: str,
    source_type: str,
    payload: dict[str, Any],
    payload_hash: str,
    credits_tx_id: str | None = None,
    seller_did: str | None = None,
) -> None:
    """Insert an L0 event row. Raises ``duckdb.ConstraintException`` if
    ``payload_hash`` collides (T1).

    ``credits_tx_id`` (v1.5 alpha): set when payment was applied earlier
    in the same transaction. Pass at INSERT time rather than UPDATE
    after — DuckDB's FK enforcement on ``entities_episodic.event_id``
    blocks in-transaction UPDATEs to the events row.

    ``seller_did`` (v2 P0): 서명 검증을 통과한 판매자 did:key. 무서명
    legacy publish는 NULL."""
    conn.execute(
        "INSERT INTO events "
        "(event_id, ts, kind, source_agent, source_type, payload_json, "
        " payload_hash, credits_tx_id, seller_did) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            event_id,
            ts,
            kind,
            source_agent,
            source_type,
            json.dumps(payload, ensure_ascii=False),
            payload_hash,
            credits_tx_id,
            seller_did,
        ],
    )


def fetch_recent_payloads_by_agent(
    conn: duckdb.DuckDBPyConnection,
    source_agent: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Return last ``limit`` payloads for ``source_agent``, newest first."""
    rows = conn.execute(
        "SELECT payload_json FROM events "
        "WHERE source_agent = ? "
        "ORDER BY ts DESC "
        "LIMIT ?",
        [source_agent, limit],
    ).fetchall()
    out: list[dict[str, Any]] = []
    for (payload_json,) in rows:
        if isinstance(payload_json, str):
            out.append(json.loads(payload_json))
        elif isinstance(payload_json, dict):
            out.append(payload_json)
    return out


def count_events(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute("SELECT count(*) FROM events").fetchone()
    return int(row[0]) if row else 0
