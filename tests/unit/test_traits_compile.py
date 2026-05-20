"""Phase 2.5 — RED tests: traits 머지 + DB 적용."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import duckdb

from app.reflection.output_schema import TraitsCompiled
from app.reflection.traits_compile import apply_traits, merge_traits


class TestMergeTraits:
    def test_merge_traits_initial_compile(self) -> None:
        existing: dict = {}
        new = TraitsCompiled(
            summary="첫 요약",
            descriptors=["감시형", "고빈도"],
            evidence_event_ids=["e1", "e2"],
        )
        merged = merge_traits(existing, new)
        assert merged["summary"] == "첫 요약"
        assert set(merged["descriptors"]) == {"감시형", "고빈도"}
        assert merged["evidence_event_ids"] == ["e1", "e2"]

    def test_merge_traits_dedupes_descriptors(self) -> None:
        existing = {
            "summary": "기존",
            "descriptors": ["감시형", "고빈도"],
            "evidence_event_ids": ["e1"],
        }
        new = TraitsCompiled(
            summary="새 요약",
            descriptors=["감시형", "자율형"],  # 감시형 중복
            evidence_event_ids=["e2"],
        )
        merged = merge_traits(existing, new)
        # 중복 제거된 descriptors
        assert sorted(merged["descriptors"]) == sorted(["감시형", "고빈도", "자율형"])
        # summary는 최신 것으로 교체
        assert merged["summary"] == "새 요약"
        # evidence 누적
        assert "e1" in merged["evidence_event_ids"]
        assert "e2" in merged["evidence_event_ids"]

    def test_merge_traits_caps_evidence_at_50(self) -> None:
        existing = {
            "summary": "old",
            "descriptors": [],
            "evidence_event_ids": [f"e{i}" for i in range(45)],
        }
        new = TraitsCompiled(
            summary="new",
            descriptors=[],
            evidence_event_ids=[f"n{i}" for i in range(20)],
        )
        merged = merge_traits(existing, new)
        # 최대 50개로 캡 (최근 것 우선 — 새 reflection의 evidence가 보존됨)
        assert len(merged["evidence_event_ids"]) == 50
        # 새 evidence는 모두 포함돼야 함
        for i in range(20):
            assert f"n{i}" in merged["evidence_event_ids"]


class TestApplyTraits:
    def test_apply_traits_inserts_when_missing(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        traits = {
            "summary": "테스트",
            "descriptors": ["감시형"],
            "evidence_event_ids": ["e1"],
        }
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        apply_traits(tmp_db, agent_id="agent_new", traits=traits, now=now)

        row = tmp_db.execute(
            "SELECT traits_json FROM entities_semantic WHERE agent_id = ?",
            ["agent_new"],
        ).fetchone()
        assert row is not None
        loaded = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert loaded["summary"] == "테스트"

    def test_apply_traits_updates_existing_row(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        # 먼저 빈 traits 행 삽입
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        tmp_db.execute(
            "INSERT INTO entities_semantic "
            "(agent_id, aliases, traits_json, source_type, corroboration_count, "
            " first_seen_ts, last_updated) "
            "VALUES (?, '[]', '{}', 'self', 1, ?, ?)",
            ["agent_existing", now, now],
        )

        traits = {
            "summary": "업데이트된 요약",
            "descriptors": ["고빈도"],
            "evidence_event_ids": [],
        }
        apply_traits(tmp_db, agent_id="agent_existing", traits=traits, now=now)

        row = tmp_db.execute(
            "SELECT traits_json FROM entities_semantic WHERE agent_id = ?",
            ["agent_existing"],
        ).fetchone()
        assert row is not None
        loaded = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert loaded["summary"] == "업데이트된 요약"
