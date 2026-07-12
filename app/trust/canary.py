"""Canary 감사 — 답을 아는 사실을 심어 되사서 왜곡을 측정 (P3).

honesty 축의 오라클 (devil's advocate C1 해소 — grounding이 아니라 canary가
판매자 정직성을 측정한다). 크라우드소싱 gold-question QC의 이식.

공격 대응 (2차 리서치 "All That Glitters Is Gold"):
  - canary는 1회용 — 재사용 금지 (통계적 지문 축적 차단)
  - 풀은 회전 — 소진되면 새로 심는다 (생성은 데모 스크립트/배치의 몫)
  - 실제 질의와 같은 유통 경로로 되산다 (구분 불가능성은 호출자 책임)

판정은 tokenize + jaccard 대조 — 결정적이고 LLM이 불필요 (mock-friendly).
LLM judge 보조 판정은 P4+에서 선택 부착 (단독 심판 금지 원칙).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb

from app.storage.dedup import tokenize
from app.trust.service import TrustUpdateResult, record_trust_event

DEFAULT_MATCH_THRESHOLD = 0.6


class CanaryAlreadyUsedError(Exception):
    """1회용 canary의 재판정 시도."""


@dataclass(frozen=True)
class CanaryRow:
    canary_id: str
    topic: str
    answer_key: dict[str, Any]
    planted_ts: datetime
    target_agent: str | None


@dataclass(frozen=True)
class CanaryVerdict:
    canary_id: str
    seller_agent: str
    passed: bool
    match_score: float
    trust: TrustUpdateResult


def plant_canary(
    conn: duckdb.DuckDBPyConnection,
    *,
    topic: str,
    answer_key: dict[str, Any],
    now: datetime,
    target_agent: str | None = None,
) -> str:
    canary_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO canary_pool "
        "(canary_id, planted_ts, topic, answer_key, used, target_agent) "
        "VALUES (?, ?, ?, ?, FALSE, ?)",
        [
            canary_id,
            now,
            topic,
            json.dumps(answer_key, ensure_ascii=False),
            target_agent,
        ],
    )
    return canary_id


def next_unused_canary(
    conn: duckdb.DuckDBPyConnection, *, topic: str | None = None
) -> CanaryRow | None:
    sql = (
        "SELECT canary_id, topic, answer_key, planted_ts, target_agent "
        "FROM canary_pool WHERE used = FALSE"
    )
    params: list[Any] = []
    if topic is not None:
        sql += " AND topic = ?"
        params.append(topic)
    sql += " ORDER BY planted_ts LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    planted_ts = row[3]
    if planted_ts.tzinfo is None:
        planted_ts = planted_ts.replace(tzinfo=UTC)
    return CanaryRow(
        canary_id=str(row[0]),
        topic=row[1],
        answer_key=json.loads(row[2]),
        planted_ts=planted_ts,
        target_agent=row[4],
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def judge_canary_response(
    conn: duckdb.DuckDBPyConnection,
    *,
    canary_id: str,
    seller_agent: str,
    response_payload: dict[str, Any],
    now: datetime,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> CanaryVerdict:
    """되사온 응답을 answer_key와 대조 → honesty trust event 기록.

    canary는 즉시 used 처리 (판정 결과와 무관하게 1회용).
    """
    row = conn.execute(
        "SELECT answer_key, used FROM canary_pool WHERE canary_id = ?",
        [canary_id],
    ).fetchone()
    if row is None:
        raise CanaryAlreadyUsedError(f"unknown canary: {canary_id}")
    if row[1]:
        raise CanaryAlreadyUsedError(f"canary already used: {canary_id}")

    answer_key: dict[str, Any] = json.loads(row[0])
    score = _jaccard(tokenize(response_payload), tokenize(answer_key))
    passed = score >= threshold

    conn.execute(
        "UPDATE canary_pool SET used = TRUE, used_ts = ? WHERE canary_id = ?",
        [now, canary_id],
    )

    trust = record_trust_event(
        conn,
        agent_id=seller_agent,
        criterion="honesty",
        positive=passed,
        weight=1.0,
        cause="canary_pass" if passed else "canary_fail",
        cause_ref=canary_id,
        now=now,
    )
    return CanaryVerdict(
        canary_id=canary_id,
        seller_agent=seller_agent,
        passed=passed,
        match_score=score,
        trust=trust,
    )
