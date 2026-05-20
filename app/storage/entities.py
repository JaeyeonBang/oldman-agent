"""L1 entity storage — episodic append + semantic upsert touch.

Like ``events.py`` helpers, no transaction management here (T2). The caller
opens BEGIN, calls these, then COMMIT (or ROLLBACK on failure).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import duckdb


def append_episodic(
    conn: duckdb.DuckDBPyConnection,
    *,
    event_id: str,
    observer_agent: str,
    observed_agent: str | None,
    kind: str,
    ts: datetime,
    source_type: str,
) -> str:
    """Insert one ``entities_episodic`` row; return the new id."""
    row_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO entities_episodic "
        "(id, event_id, observer_agent, observed_agent, kind, ts, source_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [row_id, event_id, observer_agent, observed_agent, kind, ts, source_type],
    )
    return row_id


def touch_semantic(
    conn: duckdb.DuckDBPyConnection,
    *,
    agent_id: str,
    source_type: str,
    ts: datetime,
) -> None:
    """Minimal M1 touch: insert if absent, else bump corroboration + ts."""
    existing = conn.execute(
        "SELECT corroboration_count FROM entities_semantic WHERE agent_id = ?",
        [agent_id],
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO entities_semantic "
            "(agent_id, aliases, traits_json, source_type, corroboration_count, "
            " first_seen_ts, last_updated) "
            "VALUES (?, '[]', '{}', ?, 1, ?, ?)",
            [agent_id, source_type, ts, ts],
        )
    else:
        conn.execute(
            "UPDATE entities_semantic "
            "SET corroboration_count = corroboration_count + 1, last_updated = ? "
            "WHERE agent_id = ?",
            [ts, agent_id],
        )
