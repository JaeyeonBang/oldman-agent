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

v2: ``execute_query()`` core extracted as a callable so both the deprecated
``/query`` route and the A2A AgentExecutor invoke the same render path.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import duckdb
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.schemas import QueryRequest, QueryResponse
from app.narrative.renderer import render_narrative

_LOG = logging.getLogger(__name__)

router = APIRouter()


class ProviderUnavailableError(Exception):
    """Raised when narrative_provider is not configured."""


async def execute_query(
    conn: duckdb.DuckDBPyConnection,
    narrative_provider: Any,
    req: QueryRequest,
    *,
    judge_provider: Any = None,
) -> QueryResponse:
    """Core query flow. Validates, runs renderer, applies strict-mode judge.

    Raises:
        ProviderUnavailableError if narrative_provider is None.
    """
    if narrative_provider is None:
        raise ProviderUnavailableError("narrative_provider_unconfigured")

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
        narrative_provider,
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


@router.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest, request: Request, response: Response
) -> QueryResponse:
    """Deprecated v1 route — thin wrapper around ``execute_query``.

    v2: Prefer ``POST /`` with JSON-RPC ``message/send``
    + ``metadata.oldman.intent="query"``.
    """
    response.headers["Deprecation"] = (
        "A2A-replacement; use POST / with method=message/send"
    )
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

    judge_provider = (
        getattr(request.app.state, "judge_provider", None)
        or getattr(request.app.state, "reflection_provider", None)
    )

    return await execute_query(
        conn,
        provider,
        req,
        judge_provider=judge_provider,
    )
