"""``GET /admin/memory`` — 내부 메모리 누적 가시화 (브라우저 친화).

DuckDB 단일 writer 잠금 때문에 외부 프로세스로는 파일을 못 연다. 서버가 들고
있는 연결을 그대로 써서 stats + 최근 행을 JSON으로 반환한다.

보안: ``OLDMAN_ADMIN_TOKEN`` env가 설정된 경우 쿼리스트링 ``?token=...`` 또는
``X-Admin-Token`` 헤더가 일치해야 한다. 미설정이면 공개 (dogfood 편의).
"""

from __future__ import annotations

import json
import os
from typing import Any

import duckdb
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter()


def _check_token(request: Request) -> None:
    expected = os.environ.get("OLDMAN_ADMIN_TOKEN", "")
    if not expected:
        return  # 토큰 미설정 → 공개
    provided = (
        request.query_params.get("token")
        or request.headers.get("x-admin-token", "")
    )
    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "missing or invalid admin token"},
        )


def _safe_json(raw: Any) -> Any:
    """DuckDB JSON 컬럼은 str로 올 수도 dict로 올 수도 있다."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _scalar(conn: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row else 0


@router.get("/admin/memory")
async def memory_stats(request: Request) -> dict[str, Any]:
    """내부 메모리 현황을 JSON으로 반환."""
    _check_token(request)
    conn: duckdb.DuckDBPyConnection = request.app.state.db

    counts = {
        "events": _scalar(conn, "SELECT count(*) FROM events"),
        "entities_semantic": _scalar(conn, "SELECT count(*) FROM entities_semantic"),
        "entities_episodic": _scalar(conn, "SELECT count(*) FROM entities_episodic"),
        "reflections": _scalar(conn, "SELECT count(*) FROM reflections"),
    }

    agents = [
        r[0]
        for r in conn.execute(
            "SELECT agent_id FROM entities_semantic ORDER BY last_updated DESC LIMIT 50"
        ).fetchall()
    ]

    recent_events = [
        {
            "event_id": str(r[0]),
            "ts": r[1].isoformat() if r[1] else None,
            "kind": r[2],
            "source_agent": r[3],
            "source_type": r[4],
            "payload": _safe_json(r[5]),
        }
        for r in conn.execute(
            "SELECT event_id, ts, kind, source_agent, source_type, payload_json "
            "FROM events ORDER BY ts DESC LIMIT 20"
        ).fetchall()
    ]

    recent_reflections = [
        {
            "reflection_id": str(r[0]),
            "ts": r[1].isoformat() if r[1] else None,
            "scope": r[2],
            "subject": r[3],
            "text_preview": (r[4] or "")[:300],
            "text_length": len(r[4] or ""),
        }
        for r in conn.execute(
            "SELECT reflection_id, ts, scope, subject, text "
            "FROM reflections ORDER BY ts DESC LIMIT 10"
        ).fetchall()
    ]

    traits = {
        r[0]: {
            "source_type": r[1],
            "corroboration_count": r[2],
            "first_seen_ts": r[3].isoformat() if r[3] else None,
            "last_updated": r[4].isoformat() if r[4] else None,
            "aliases": _safe_json(r[5]),
            "traits_json": _safe_json(r[6]),
        }
        for r in conn.execute(
            "SELECT agent_id, source_type, corroboration_count, "
            "first_seen_ts, last_updated, aliases, traits_json "
            "FROM entities_semantic ORDER BY last_updated DESC LIMIT 20"
        ).fetchall()
    }

    return {
        "counts": counts,
        "agents": agents,
        "recent_events": recent_events,
        "recent_reflections": recent_reflections,
        "traits_compiled": traits,
    }


@router.get("/admin/trust")
async def trust_overview(request: Request) -> dict[str, Any]:
    """v2 신뢰 시스템 관측: 마을 명부 + ledger + 최근 신뢰 이벤트 + 회계 감사.

    점수는 원시 (alpha, beta)와 함께 mean/lower_bound를 계산해 노출 — 외부
    소비자용 정본 점수가 아니라 운영자 대시보드다 (꼰대의 공개 발화는
    어디까지나 주관적 narrative)."""
    _check_token(request)
    conn: duckdb.DuckDBPyConnection = request.app.state.db

    from app.credits.audit import audit_credits
    from app.trust.ledger import BetaScore

    registry = [
        {
            "agent_id": r[0],
            "state": r[1],
            "violation_count": r[2],
            "joined_at": r[3].isoformat() if r[3] else None,
            "state_changed_at": r[4].isoformat() if r[4] else None,
        }
        for r in conn.execute(
            "SELECT agent_id, state, violation_count, joined_at, state_changed_at "
            "FROM village_registry ORDER BY state_changed_at DESC"
        ).fetchall()
    ]

    scores = [
        {
            "agent_id": r[0],
            "criterion": r[1],
            "alpha": r[2],
            "beta": r[3],
            "mean": round(BetaScore(alpha=r[2], beta=r[3]).mean, 3),
            "lower_bound": round(BetaScore(alpha=r[2], beta=r[3]).lower_bound(), 3),
            "last_update_ts": r[4].isoformat() if r[4] else None,
        }
        for r in conn.execute(
            "SELECT agent_id, criterion, alpha, beta, last_update_ts "
            "FROM trust_ledger ORDER BY agent_id, criterion"
        ).fetchall()
    ]

    recent_trust_events = [
        {
            "trust_event_id": str(r[0]),
            "ts": r[1].isoformat() if r[1] else None,
            "agent_id": r[2],
            "criterion": r[3],
            "positive": bool(r[4]),
            "weight": r[5],
            "cause": r[6],
            "cause_ref": r[7],
        }
        for r in conn.execute(
            "SELECT trust_event_id, ts, agent_id, criterion, positive, weight, "
            "cause, cause_ref FROM trust_events ORDER BY ts DESC LIMIT 30"
        ).fetchall()
    ]

    escrows = {
        r[0]: {"count": r[1], "amount": r[2]}
        for r in conn.execute(
            "SELECT status, count(*), COALESCE(SUM(amount), 0) "
            "FROM royalty_escrows GROUP BY status"
        ).fetchall()
    }

    audit = audit_credits(conn)
    return {
        "village_registry": registry,
        "trust_scores": scores,
        "recent_trust_events": recent_trust_events,
        "escrows_by_status": escrows,
        "credits_audit": {
            "balanced": audit.balanced,
            "total_balance": audit.total_balance,
            "total_minted": audit.total_minted,
            "open_escrow_liability": audit.open_escrow_liability,
            "issues": audit.issues,
        },
    }
