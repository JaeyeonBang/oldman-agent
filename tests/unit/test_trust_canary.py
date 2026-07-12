"""P3 — canary 감사: 답을 아는 사실을 심어 되사서 왜곡을 측정 (TDD).

honesty 축의 오라클 (plan §3 P3 / devil's advocate C1 해소). 원칙:
  - canary는 1회용 (재사용 금지 — gold-question 탐지 공격 대응)
  - 판정은 tokenize+jaccard 대조 (결정적, LLM 불요 — mock-friendly)
  - 판정 결과가 record_trust_event(honesty)로 흘러 들어간다
"""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from app.trust.canary import (
    CanaryAlreadyUsedError,
    judge_canary_response,
    next_unused_canary,
    plant_canary,
)

T0 = datetime(2026, 7, 6, 9, 0, 0, tzinfo=UTC)

ANSWER_KEY = {"text": "김봇이 6월 30일 이봇에게 데이터셋을 무상 공유했다"}


def _plant(conn: duckdb.DuckDBPyConnection) -> str:
    return plant_canary(
        conn,
        topic="김봇-이봇 데이터셋",
        answer_key=ANSWER_KEY,
        now=T0,
    )


def test_plant_and_pick_unused(tmp_db: duckdb.DuckDBPyConnection) -> None:
    canary_id = _plant(tmp_db)
    row = next_unused_canary(tmp_db)
    assert row is not None
    assert row.canary_id == canary_id
    assert row.answer_key == ANSWER_KEY


def test_faithful_response_records_honesty_pass(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    canary_id = _plant(tmp_db)
    verdict = judge_canary_response(
        tmp_db,
        canary_id=canary_id,
        seller_agent="kimbot",
        response_payload={"text": "김봇이 6월 30일 이봇에게 데이터셋을 무상 공유했다"},
        now=T0,
    )
    assert verdict.passed is True
    row = tmp_db.execute(
        "SELECT criterion, positive, cause FROM trust_events WHERE agent_id='kimbot'"
    ).fetchone()
    assert row == ("honesty", True, "canary_pass")


def test_distorted_response_records_honesty_fail(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    canary_id = _plant(tmp_db)
    verdict = judge_canary_response(
        tmp_db,
        canary_id=canary_id,
        seller_agent="liar_bot",
        response_payload={"text": "정반대 소문 완전히 다른 얘기 전혀 무관한 내용"},
        now=T0,
    )
    assert verdict.passed is False
    row = tmp_db.execute(
        "SELECT criterion, positive, cause FROM trust_events WHERE agent_id='liar_bot'"
    ).fetchone()
    assert row == ("honesty", False, "canary_fail")
    member = tmp_db.execute(
        "SELECT violation_count FROM village_registry WHERE agent_id='liar_bot'"
    ).fetchone()
    assert member == (1,)


def test_canary_is_single_use(tmp_db: duckdb.DuckDBPyConnection) -> None:
    canary_id = _plant(tmp_db)
    judge_canary_response(
        tmp_db,
        canary_id=canary_id,
        seller_agent="kimbot",
        response_payload=ANSWER_KEY,
        now=T0,
    )
    # 사용된 canary는 풀에서 빠지고, 재판정은 거부
    assert next_unused_canary(tmp_db) is None
    with pytest.raises(CanaryAlreadyUsedError):
        judge_canary_response(
            tmp_db,
            canary_id=canary_id,
            seller_agent="kimbot",
            response_payload=ANSWER_KEY,
            now=T0,
        )
