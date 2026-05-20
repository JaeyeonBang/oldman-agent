"""``POST /publish`` — A2A event ingest with rule blocklist + Jaccard dedup.

::

    Publish flow:
      request ──▶ pydantic validate ──▶ blocklist gate ──▶ tokenize + Jaccard scan
                                                               │
                                                               ▼
                                                     BEGIN TX ─────────┐
                                                       insert L0       │
                                                       append L1b      │
                                                       touch L1a       │
                                                     COMMIT ───────────┘
                                                               │
                                                               ▼
                                          200 stored | 409 dedup | 422 blocked
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any

import duckdb
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.api.schemas import PublishRequest, PublishResponse
from app.config import Settings
from app.reflection.scheduler import maybe_run_reflection
from app.storage import entities as ent_store
from app.storage import events as evt_store
from app.storage.dedup import (
    BLOCKLISTED_KINDS,
    is_near_duplicate,
    payload_sha256,
    tokenize,
)

router = APIRouter()


async def _run_reflections_for_publish(
    conn: duckdb.DuckDBPyConnection,
    provider: Any,
    *,
    source_agent: str,
    observed_agent: str | None,
    done_event: Any = None,
) -> None:
    """publish 후 1~3개 scope에 대해 reflection 트리거 검사.

    LLM 예외는 scheduler에서 swallow. publish 흐름은 이미 200 응답 후.
    """
    try:
        # agent-scope: source_agent
        await maybe_run_reflection(
            conn, scope="agent", subject=source_agent, provider=provider
        )
        # agent-scope: observed_agent (있다면)
        if observed_agent:
            await maybe_run_reflection(
                conn, scope="agent", subject=observed_agent, provider=provider
            )
            # pair-scope
            pair_subject = f"{source_agent}:{observed_agent}"
            await maybe_run_reflection(
                conn, scope="pair", subject=pair_subject, provider=provider
            )
        # society-scope
        await maybe_run_reflection(
            conn, scope="society", subject="global", provider=provider
        )
    finally:
        if done_event is not None:
            with contextlib.suppress(Exception):
                done_event.set()


@router.post(
    "/publish",
    response_model=PublishResponse,
    responses={
        409: {"model": PublishResponse},
        422: {"model": PublishResponse},
    },
)
async def publish(
    req: PublishRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> PublishResponse:
    # 1. blocklist
    if req.event_kind in BLOCKLISTED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"status": "blocked", "reason": "blocklisted_kind"},
        )

    conn: duckdb.DuckDBPyConnection = request.app.state.db
    settings: Settings = request.app.state.settings

    # 2. compute hash + tokens
    p_hash = payload_sha256(req.payload)
    new_tokens = tokenize(req.payload)

    # 3. Jaccard near-dup scan
    recent = evt_store.fetch_recent_payloads_by_agent(
        conn, req.source_agent, settings.jaccard_window
    )
    recent_tokens = [tokenize(p) for p in recent]
    if is_near_duplicate(new_tokens, recent_tokens, settings.jaccard_threshold):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "deduplicated", "reason": "jaccard_near_duplicate"},
        )

    # 4. assign id + ts
    event_id = str(uuid.uuid4())
    ts = req.ts or datetime.now(UTC)

    # 5. T2: explicit transaction; T1: rely on UNIQUE + IntegrityError
    try:
        conn.execute("BEGIN")
        evt_store.insert_event(
            conn,
            event_id=event_id,
            ts=ts,
            kind=req.event_kind,
            source_agent=req.source_agent,
            source_type=req.declared_source_type,
            payload=req.payload,
            payload_hash=p_hash,
        )
        ent_store.append_episodic(
            conn,
            event_id=event_id,
            observer_agent=req.source_agent,
            observed_agent=req.observed_agent,
            kind=req.event_kind,
            ts=ts,
            source_type=req.declared_source_type,
        )
        ent_store.touch_semantic(
            conn,
            agent_id=req.source_agent,
            source_type=req.declared_source_type,
            ts=ts,
        )
        if req.observed_agent:
            ent_store.touch_semantic(
                conn,
                agent_id=req.observed_agent,
                source_type=req.declared_source_type,
                ts=ts,
            )
        conn.execute("COMMIT")
    except duckdb.ConstraintException as e:
        conn.execute("ROLLBACK")
        # BUG-2 fix v1.0.3: only payload_hash UNIQUE collisions map to exact_hash dedup.
        # Other constraint violations (PK, CHECK, FK) must re-raise → 500 (system bug,
        # not dedup). Prior version matched "duplicate"/"unique" substrings which
        # misclassified event_id PK collisions as exact_hash.
        msg = str(e).lower()
        if "payload_hash" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "deduplicated", "reason": "exact_hash"},
            ) from e
        raise
    except Exception:
        with contextlib.suppress(duckdb.Error):
            conn.execute("ROLLBACK")
        raise

    # 6. M2: 백그라운드 reflection 스케줄링 (publish 응답 전송 후 실행)
    provider = getattr(request.app.state, "reflection_provider", None)
    if provider is not None:
        done_event = getattr(request.app.state, "reflection_done", None)
        background_tasks.add_task(
            _run_reflections_for_publish,
            conn,
            provider,
            source_agent=req.source_agent,
            observed_agent=req.observed_agent,
            done_event=done_event,
        )

    return PublishResponse(status="stored", event_id=event_id)
