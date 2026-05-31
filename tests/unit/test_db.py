"""Phase 1.2 RED: migration runner + schema invariants (incl. T1 UNIQUE)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


def _tables(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
    ).fetchall()
    return {r[0] for r in rows}


def test_apply_migrations_creates_all_tables(tmp_path: Path) -> None:
    from app.storage.db import apply_migrations, get_conn

    conn = get_conn(str(tmp_path / "t.duckdb"))
    apply_migrations(conn)
    tables = _tables(conn)
    for required in (
        "_schema_version",
        "events",
        "entities_semantic",
        "entities_episodic",
        "reflections",
    ):
        assert required in tables, f"missing table: {required}"


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    from app.storage.db import apply_migrations, get_conn

    db_file = tmp_path / "t.duckdb"
    conn = get_conn(str(db_file))
    apply_migrations(conn)
    first = conn.execute("SELECT count(*) FROM _schema_version").fetchone()
    apply_migrations(conn)  # second call must not raise
    second = conn.execute("SELECT count(*) FROM _schema_version").fetchone()
    assert first is not None and second is not None
    assert first[0] == second[0], "second apply_migrations must not re-apply"
    assert first[0] >= 1, "at least one migration must have been applied"


def test_payload_hash_has_unique_constraint(tmp_path: Path) -> None:
    """T1 regression: events.payload_hash must be UNIQUE."""
    from app.storage.db import apply_migrations, get_conn

    conn = get_conn(str(tmp_path / "t.duckdb"))
    apply_migrations(conn)

    insert_sql = (
        "INSERT INTO events "
        "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (uuid(), now(), 'chat', 'a', 'self', '{}', 'samehash')"
    )
    conn.execute(insert_sql)
    with pytest.raises(duckdb.Error):
        conn.execute(insert_sql)
