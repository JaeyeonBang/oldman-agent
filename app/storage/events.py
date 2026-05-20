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
) -> None:
    """Insert an L0 event row. Raises ``duckdb.ConstraintException`` if
    ``payload_hash`` collides (T1)."""
    conn.execute(
        "INSERT INTO events "
        "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            event_id,
            ts,
            kind,
            source_agent,
            source_type,
            json.dumps(payload, ensure_ascii=False),
            payload_hash,
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
