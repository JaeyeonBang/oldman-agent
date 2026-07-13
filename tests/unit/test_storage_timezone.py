"""C1 회귀 — 비-UTC 호스트에서 TIMESTAMP round-trip skew 방지.

DuckDB Python 드라이버는 tz-aware datetime을 프로세스 로컬 TZ로 변환해 naive
TIMESTAMP로 저장한다. get_conn이 세션 TZ를 UTC로 고정하지 않으면, KST(UTC+9)
같은 호스트에서 저장/조회에 offset만큼 skew가 생겨 decay 계산이 손상된다.
이 테스트는 UTC CI가 아닌 환경(강제 KST)에서 skew=0을 보장한다.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest


@pytest.fixture()
def kst_host() -> Iterator[None]:
    """프로세스 타임존을 Asia/Seoul(UTC+9)로 강제 — teardown에서 복원."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Seoul"
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        if hasattr(time, "tzset"):
            time.tzset()


def test_utc_aware_timestamp_roundtrips_without_skew(
    kst_host: None, tmp_path: Path
) -> None:
    from app.storage.db import get_conn

    conn = get_conn(str(tmp_path / "tz.duckdb"))
    try:
        conn.execute("CREATE TABLE t(ts TIMESTAMP)")
        src = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        conn.execute("INSERT INTO t VALUES (?)", [src])
        back = conn.execute("SELECT ts FROM t").fetchone()[0]
    finally:
        conn.close()

    # naive로 조회된 값은 UTC wall-clock과 동일해야 한다 (offset skew 없음).
    assert back == datetime(2026, 1, 1, 0, 0, 0)
