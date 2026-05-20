"""``POST /query`` — 에이전트 행적 내러티브 조회 — Phase 3.5 / M4 확장.

::

    Query flow:
      request ──▶ pydantic validate ──▶ 503 if no provider
                                              │
                                              ▼
                                    render_narrative()
                                      cold-start? → fallback
                                      evidence empty? → fallback
                                      LLM + validate loop
                                        (strict_mode=True → judge 검증)
                                              │
                                              ▼
                                    200 QueryResponse

M4: strict_mode=True(기본)이면 app.state.judge_provider를 주입.
    judge_provider 미설정 시 existence-only로 downgrade (경고 로그).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status

from app.api.schemas import QueryRequest, QueryResponse
from app.narrative.renderer import render_narrative

_LOG = logging.getLogger(__name__)

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, request: Request) -> QueryResponse:
    """에이전트 행적 또는 소사이어티 동향을 내러티브로 반환한다.

    - ``narrative_provider`` 가 ``app.state`` 에 없으면 503.
    - DB가 cold-start 상태 (이벤트·reflection 없음)이면 fallback 메시지 반환.
    - 인용 검증 실패 시 최대 2회 재시도 후 fallback.
    - ``strict_mode=True`` (기본)이면 LLM judge 기반 내용 검증.
      judge_provider 미설정 시 existence-only로 downgrade.
    """
    conn = request.app.state.db
    provider = getattr(request.app.state, "narrative_provider", None)

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unavailable",
                "reason": "narrative_provider_unconfigured",
            },
        )

    # judge provider 결정: judge_provider → reflection_provider → None
    judge_provider = (
        getattr(request.app.state, "judge_provider", None)
        or getattr(request.app.state, "reflection_provider", None)
    )

    # strict_mode 결정
    validator_mode: Literal["existence", "strict"]
    if req.strict_mode and judge_provider is None:
        _LOG.warning(
            "query: strict_mode=True이나 judge_provider 미설정 → existence-only로 downgrade"
        )
        validator_mode = "existence"
    elif req.strict_mode:
        validator_mode = "strict"
    else:
        validator_mode = "existence"

    result = await render_narrative(
        conn,
        provider,
        req.question,
        req.subject_agent,
        max_retries=2,
        validator_mode=validator_mode,
        judge_provider=judge_provider if validator_mode == "strict" else None,
    )

    return QueryResponse(
        answer=result.answer,
        citations=result.citations,
        is_cold_start=result.is_cold_start,
        retries_used=result.retries_used,
        used_fallback=result.used_fallback,
    )
