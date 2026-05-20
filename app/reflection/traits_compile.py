"""Traits merge + apply — Phase 2.5.

merge_traits: 기존 traits dict와 새 TraitsCompiled 모델을 병합.
apply_traits: 병합된 traits를 entities_semantic.traits_json에 영속화.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import duckdb

from app.reflection.output_schema import TraitsCompiled

_EVIDENCE_CAP = 50


def merge_traits(existing: dict[str, Any], new: TraitsCompiled) -> dict[str, Any]:
    """기존 traits dict + 새 reflection 결과를 병합한다.

    병합 규칙:
    - summary: 최신 reflection의 summary로 교체 (역사적 누적은 reflections 테이블에 있음)
    - descriptors: 중복 제거 후 union (순서 보존: 기존 → 새것)
    - evidence_event_ids: 누적 후 최대 _EVIDENCE_CAP(50)개로 캡 (최근 것 우선)
    """
    # 기존 필드 안전 추출
    old_descriptors = list(existing.get("descriptors", []))
    old_evidence = list(existing.get("evidence_event_ids", []))

    # descriptors union (중복 제거, 순서 보존)
    seen: set[str] = set()
    merged_descriptors: list[str] = []
    for d in old_descriptors + list(new.descriptors):
        if d not in seen:
            merged_descriptors.append(d)
            seen.add(d)

    # evidence 누적: 새 것을 우선 보존, 그 다음 기존 것
    combined_evidence = list(new.evidence_event_ids) + old_evidence
    # 중복 제거 (순서 보존)
    evidence_seen: set[str] = set()
    deduped_evidence: list[str] = []
    for eid in combined_evidence:
        if eid not in evidence_seen:
            deduped_evidence.append(eid)
            evidence_seen.add(eid)
    capped_evidence = deduped_evidence[:_EVIDENCE_CAP]

    return {
        "summary": new.summary,
        "descriptors": merged_descriptors,
        "evidence_event_ids": capped_evidence,
    }


def apply_traits(
    conn: duckdb.DuckDBPyConnection,
    *,
    agent_id: str,
    traits: dict[str, Any],
    now: datetime,
) -> None:
    """병합된 traits를 entities_semantic.traits_json에 영속화한다.

    행이 없으면 INSERT (corroboration_count=1, source_type='third_party'),
    있으면 traits_json + last_updated만 UPDATE.

    Note: 이 함수는 호출자가 BEGIN/COMMIT을 관리한다고 가정한다 (M1 패턴).
    """
    traits_json = json.dumps(traits, ensure_ascii=False)
    existing = conn.execute(
        "SELECT 1 FROM entities_semantic WHERE agent_id = ?",
        [agent_id],
    ).fetchone()

    if existing is None:
        conn.execute(
            "INSERT INTO entities_semantic "
            "(agent_id, aliases, traits_json, source_type, corroboration_count, "
            " first_seen_ts, last_updated) "
            "VALUES (?, '[]', ?, 'third_party', 1, ?, ?)",
            [agent_id, traits_json, now, now],
        )
    else:
        conn.execute(
            "UPDATE entities_semantic "
            "SET traits_json = ?, last_updated = ? WHERE agent_id = ?",
            [traits_json, now, agent_id],
        )
