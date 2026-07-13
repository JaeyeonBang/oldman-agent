"""DuckDB connection + minimal migration runner.

DuckDB single-writer: open one connection per process, run with ``uvicorn
--workers 1``. Migrations are raw SQL under ``app/storage/migrations/`` named
``NNN_<slug>.sql``. ``_schema_version`` records applied versions; the runner
is idempotent.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")


def get_conn(db_path: str) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(db_path)
    # 세션 타임존을 UTC로 고정. DuckDB 드라이버는 tz-aware datetime을 프로세스
    # 로컬 TZ로 변환해 naive TIMESTAMP로 저장하므로, 비-UTC 호스트(예: KST)에서는
    # offset만큼 skew가 생겨 decay 계산이 손상된다. UTC 고정으로 변환을 identity화.
    conn.execute("SET TimeZone='UTC'")
    return conn


def _discover_migrations() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for p in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        m = _VERSION_RE.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    return sorted(found, key=lambda x: x[0])


def apply_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply all unapplied migrations in version order. Idempotent."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version ("
        "  version INTEGER PRIMARY KEY,"
        "  applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    applied = {
        r[0] for r in conn.execute("SELECT version FROM _schema_version").fetchall()
    }
    for version, path in _discover_migrations():
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.execute(sql)
        conn.execute("INSERT INTO _schema_version(version) VALUES (?)", [version])
