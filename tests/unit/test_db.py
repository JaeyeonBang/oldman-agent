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


def test_failed_migration_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L2 회귀 — 중간에 실패하는 마이그레이션은 부분 상태를 남기면 안 된다.
    (부분 반영 + 버전 미기록이면 재실행도 실패해 스키마가 갈린다.)"""
    from app.storage import db as dbmod
    from app.storage.db import apply_migrations, get_conn

    conn = get_conn(str(tmp_path / "t.duckdb"))
    apply_migrations(conn)  # 정상 마이그레이션 먼저

    bad = tmp_path / "999_bad.sql"
    # 첫 문장은 유효(테이블 생성), 둘째 문장은 런타임 실패(없는 테이블 참조)
    bad.write_text(
        "CREATE TABLE zzz_partial(x INTEGER);\n"
        "INSERT INTO zzz_nonexistent VALUES (1);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dbmod, "_discover_migrations", lambda: [(999, bad)])

    with pytest.raises(duckdb.Error):
        apply_migrations(conn)

    tables = {
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
    }
    assert "zzz_partial" not in tables  # 부분 반영 롤백돼야 함
    versions = {
        r[0] for r in conn.execute("SELECT version FROM _schema_version").fetchall()
    }
    assert 999 not in versions


def test_credits_from_to_indexes_survive_table_recreation(tmp_path: Path) -> None:
    """M5 회귀 — 006/008이 credits_transactions를 재생성하며 idx_credits_tx_from/
    to 인덱스를 떨어뜨리고 재생성하지 않았다. from_agent로 GROUP/필터하는 감사·
    admin 쿼리가 full scan이 되므로, 마이그레이션 후에도 두 인덱스가 존재해야 한다.
    """
    from app.storage.db import apply_migrations, get_conn

    conn = get_conn(str(tmp_path / "t.duckdb"))
    apply_migrations(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE table_name = 'credits_transactions'"
        ).fetchall()
    }
    assert "idx_credits_tx_from" in names, names
    assert "idx_credits_tx_to" in names, names


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
