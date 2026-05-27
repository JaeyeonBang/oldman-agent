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

v2: ``execute_publish()`` core extracted as a callable so both the deprecated
``/publish`` route and the A2A AgentExecutor invoke the same path. Domain
errors raise ``PublishError`` subclasses; the route wrapper maps them to
HTTPException, the executor maps them to Task ack Messages.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import duckdb

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

# ── domain errors ───────────────────────────────────────────────────────────


class PublishError(Exception):
    """Base for publish domain errors. Carries status + reason for client surface."""

    status_text: str
    reason: str

    def __init__(self, status_text: str, reason: str) -> None:
        super().__init__(f"{status_text}: {reason}")
        self.status_text = status_text
        self.reason = reason


class BlockedKindError(PublishError):
    def __init__(self) -> None:
        super().__init__("blocked", "blocklisted_kind")


class JaccardDuplicateError(PublishError):
    def __init__(self) -> None:
        super().__init__("deduplicated", "jaccard_near_duplicate")


class ExactHashDuplicateError(PublishError):
    def __init__(self) -> None:
        super().__init__("deduplicated", "exact_hash")


# ── reflection scheduling ───────────────────────────────────────────────────


async def _run_reflections_for_publish(
    conn: duckdb.DuckDBPyConnection,
    provider: Any,
    *,
    source_agent: str,
    observed_agent: str | None,
    done_event: Any = None,
) -> None:
    """publish 후 1~3개 scope에 대해 reflection 트리거 검사.

    LLM 예외는 scheduler에서 swallow. publish 흐름은 이미 응답 후.
    """
    try:
        await maybe_run_reflection(
            conn, scope="agent", subject=source_agent, provider=provider
        )
        if observed_agent:
            await maybe_run_reflection(
                conn, scope="agent", subject=observed_agent, provider=provider
            )
            pair_subject = f"{source_agent}:{observed_agent}"
            await maybe_run_reflection(
                conn, scope="pair", subject=pair_subject, provider=provider
            )
        await maybe_run_reflection(
            conn, scope="society", subject="global", provider=provider
        )
    finally:
        if done_event is not None:
            with contextlib.suppress(Exception):
                done_event.set()


# ── core (extracted for executor reuse) ─────────────────────────────────────


async def execute_publish(
    conn: duckdb.DuckDBPyConnection,
    settings: Settings,
    req: PublishRequest,
    *,
    reflection_provider: Any = None,
    reflection_done_event: Any = None,
    schedule_reflection: Callable[[Callable[[], Awaitable[None]]], None] | None = None,
) -> PublishResponse:
    """Core publish flow. Validates, dedups, persists, schedules reflection.

    Args:
        schedule_reflection: callable receiving an already-bound 0-arg coroutine
            factory. Deprecated route passes a wrapper around
            ``BackgroundTasks.add_task``; executor passes
            ``asyncio.create_task``-equivalent. If None, reflection is not
            scheduled.

    Raises:
        BlockedKindError, JaccardDuplicateError, ExactHashDuplicateError
    """
    # 1. blocklist
    if req.event_kind in BLOCKLISTED_KINDS:
        raise BlockedKindError()

    # 2. compute hash + tokens
    p_hash = payload_sha256(req.payload)
    new_tokens = tokenize(req.payload)

    # 3. Jaccard near-dup scan
    recent = evt_store.fetch_recent_payloads_by_agent(
        conn, req.source_agent, settings.jaccard_window
    )
    recent_tokens = [tokenize(p) for p in recent]
    if is_near_duplicate(new_tokens, recent_tokens, settings.jaccard_threshold):
        raise JaccardDuplicateError()

    # 4. assign id + ts
    event_id = str(uuid.uuid4())
    ts = req.ts or datetime.now(UTC)

    # 5. transaction
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
        msg = str(e).lower()
        if "payload_hash" in msg:
            raise ExactHashDuplicateError() from e
        raise
    except Exception:
        with contextlib.suppress(duckdb.Error):
            conn.execute("ROLLBACK")
        raise

    # 6. background reflection
    if reflection_provider is not None and schedule_reflection is not None:
        async def _do_reflection() -> None:
            await _run_reflections_for_publish(
                conn,
                reflection_provider,
                source_agent=req.source_agent,
                observed_agent=req.observed_agent,
                done_event=reflection_done_event,
            )
        schedule_reflection(_do_reflection)

    return PublishResponse(status="stored", event_id=event_id)


# v2.1: deprecated ``/publish`` HTTP route removed. Use JSON-RPC ``message/send``
# with ``metadata.oldman.intent="publish"`` at POST /. ``execute_publish`` above
# remains as the core domain function called by ``app/a2a/executor.py``.
