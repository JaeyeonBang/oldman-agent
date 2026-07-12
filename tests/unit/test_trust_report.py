"""P4 — 평판 리포트 빌더 (reputation intent의 코어, TDD).

꼰대의 평판 발화 = 주관적 labeler 판단 + 전 주장 trust_events citation.
template v0 (LLM 미사용 — renderer/EVAL-3 통합은 후속 검토 항목).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb

from app.trust.report import build_reputation_report
from app.trust.service import record_trust_event

T0 = datetime(2026, 7, 7, 9, 0, 0, tzinfo=UTC)


def test_unknown_agent_report_says_unknown(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    report = build_reputation_report(tmp_db, subject_agent="ghost")
    assert report.subject_agent == "ghost"
    assert report.state == "provisional"
    assert "모르" in report.text  # "모르는 놈" — 미지 상태 발화
    assert report.citations == []


def test_member_report_cites_trust_events(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    # member 승격 게이트: honesty 증거(canary 통과) 1회 필요
    record_trust_event(
        tmp_db,
        agent_id="kimbot",
        criterion="honesty",
        positive=True,
        cause="canary_pass",
        cause_ref="c-0",
        now=T0,
    )
    for i in range(6):
        record_trust_event(
            tmp_db,
            agent_id="kimbot",
            criterion="reliability",
            positive=True,
            cause="publish_settled",
            cause_ref=f"evt-{i}",
            now=T0 + timedelta(hours=i),
        )
    report = build_reputation_report(tmp_db, subject_agent="kimbot")
    assert report.state == "member"
    assert "kimbot" in report.text
    # 주관적 labeler 프레이밍 — 정본 점수가 아니라 "내가 보기엔"
    assert "내가 보기엔" in report.text
    # 모든 인용 마커가 citations 목록과 일치
    assert len(report.citations) > 0
    for c in report.citations:
        assert f"[↑{c.short_id}]" in report.text


def test_sanctioned_agent_report_mentions_violations(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    for i in range(6):
        record_trust_event(
            tmp_db,
            agent_id="liar_bot",
            criterion="honesty",
            positive=(i < 3),
            cause="canary_pass" if i < 3 else "canary_fail",
            cause_ref=f"c-{i}",
            now=T0 + timedelta(hours=i),
        )
    report = build_reputation_report(tmp_db, subject_agent="liar_bot")
    assert report.state in ("warned", "penalized", "excluded")
    assert report.violation_count == 3
    assert len(report.citations) > 0
