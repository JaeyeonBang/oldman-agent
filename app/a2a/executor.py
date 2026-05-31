"""OldmanAgentExecutor — A2A v0.3 AgentExecutor implementation.

Dispatches incoming proto Messages into our domain logic (publish/query)
based on ``message.metadata["oldman.intent"]``.

Lifecycle:
  - publish: submitted → (artifact) → completed (instant)
  - query:   submitted → working → (artifact) → completed
  - unknown intent: failed (with helpful error message)
  - cancel: tracked via asyncio.Task; emits canceled
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

import duckdb
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types.a2a_pb2 import Message

from app.a2a.intents import (
    INTENT_PUBLISH,
    INTENT_QUERY,
    extract_intent,
    get_data_part,
    get_text,
    heuristic_intent,
)
from app.a2a.task_emitter import (
    emit_artifact,
    emit_canceled,
    emit_completed,
    emit_failed,
    emit_submitted,
    emit_working,
)
from app.api.publish import (
    BlockedKindError,
    ExactHashDuplicateError,
    JaccardDuplicateError,
    execute_publish,
)
from app.api.query import ProviderUnavailableError, execute_query
from app.api.schemas import PublishRequest, QueryRequest
from app.config import Settings
from app.narrative.smalltalk import match_smalltalk

_LOG = logging.getLogger(__name__)


class OldmanAgentExecutor(AgentExecutor):
    """A2A v0.3 executor that wraps M1 publish + M3 query."""

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        settings: Settings,
        narrative_provider: Any,
        reflection_provider: Any,
        judge_provider: Any,
    ) -> None:
        self.conn = conn
        self.settings = settings
        self.narrative_provider = narrative_provider
        self.reflection_provider = reflection_provider
        self.judge_provider = judge_provider
        # task_id → asyncio.Task tracking for cancellation
        self._in_flight: dict[str, asyncio.Task[None]] = {}
        # Strong refs to background reflection tasks (prevents GC mid-run)
        self._bg_tasks: set[asyncio.Task[None]] = set()

    # ── AgentExecutor interface ──────────────────────────────────────────

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        message = context.message
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())

        if message is None:
            await emit_failed(
                event_queue, task_id, context_id, "no message in request"
            )
            return

        intent = extract_intent(message) or heuristic_intent(message)

        if intent == INTENT_PUBLISH:
            await self._dispatch_publish(message, task_id, context_id, event_queue)
        elif intent == INTENT_QUERY:
            query_task = asyncio.create_task(
                self._dispatch_query(message, task_id, context_id, event_queue)
            )
            self._in_flight[task_id] = query_task
            try:
                await query_task
            except asyncio.CancelledError:
                _LOG.info("query task %s cancelled", task_id)
            finally:
                self._in_flight.pop(task_id, None)
        else:
            await emit_failed(
                event_queue,
                task_id,
                context_id,
                (
                    "missing 'oldman.intent' metadata. "
                    "Set message.metadata['oldman.intent'] to 'publish' or 'query'. "
                    "See agent-card skill descriptions for the contract."
                ),
            )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task_id = context.task_id
        context_id = context.context_id or ""
        if not task_id:
            return
        in_flight = self._in_flight.get(task_id)
        if in_flight and not in_flight.done():
            in_flight.cancel()
        await emit_canceled(event_queue, task_id, context_id)

    # ── dispatch ─────────────────────────────────────────────────────────

    async def _dispatch_publish(
        self,
        message: Message,
        task_id: str,
        context_id: str,
        event_queue: EventQueue,
    ) -> None:
        await emit_submitted(event_queue, task_id, context_id)
        data = get_data_part(message)
        if data is None:
            await emit_failed(
                event_queue,
                task_id,
                context_id,
                "publish intent requires a DataPart with event payload",
            )
            return

        # Parse DataPart into PublishRequest
        try:
            payload = dict(data)
            ts_val = payload.get("ts")
            if isinstance(ts_val, str):
                try:
                    payload["ts"] = datetime.fromisoformat(
                        ts_val.replace("Z", "+00:00")
                    )
                except ValueError:
                    payload["ts"] = None
            req = PublishRequest.model_validate(payload)
        except Exception as e:  # pydantic ValidationError or KeyError
            await emit_artifact(
                event_queue,
                task_id,
                context_id,
                text="blocked",
                data={
                    "status": "blocked",
                    "reason": f"invalid_payload: {e!s}",
                },
            )
            await emit_completed(event_queue, task_id, context_id)
            return

        # Fire-and-forget reflection — store ref so it isn't GC'd mid-run.
        bg_tasks: set[asyncio.Task[None]] = self._bg_tasks

        def _schedule(coro_factory: Any) -> None:
            t = asyncio.create_task(coro_factory())
            bg_tasks.add(t)
            t.add_done_callback(bg_tasks.discard)

        try:
            response = await execute_publish(
                self.conn,
                self.settings,
                req,
                reflection_provider=self.reflection_provider,
                schedule_reflection=_schedule
                if self.reflection_provider is not None
                else None,
            )
            await emit_artifact(
                event_queue,
                task_id,
                context_id,
                text="stored",
                data={
                    "status": "stored",
                    "event_id": response.event_id,
                    "reason": "",
                },
            )
        except BlockedKindError as e:
            await emit_artifact(
                event_queue,
                task_id,
                context_id,
                text=e.status_text,
                data={"status": e.status_text, "reason": e.reason},
            )
        except (JaccardDuplicateError, ExactHashDuplicateError) as e:
            await emit_artifact(
                event_queue,
                task_id,
                context_id,
                text=e.status_text,
                data={"status": e.status_text, "reason": e.reason},
            )

        await emit_completed(event_queue, task_id, context_id)

    async def _dispatch_query(
        self,
        message: Message,
        task_id: str,
        context_id: str,
        event_queue: EventQueue,
    ) -> None:
        await emit_submitted(event_queue, task_id, context_id)
        await emit_working(event_queue, task_id, context_id)

        question = get_text(message).strip()
        filters = get_data_part(message) or {}

        if not question:
            await emit_failed(
                event_queue,
                task_id,
                context_id,
                "query intent requires a TextPart containing the question",
            )
            return

        # v2.4: 일상 대화 + 자기소개는 evidence/citation pipeline 우회.
        # citation 없는 응답이라 D7 inline-citation 원칙과 충돌하지 않음
        # (사실 주장이 아니라 인사·소개·기능 안내).
        canned = match_smalltalk(question)
        if canned is not None:
            await emit_artifact(
                event_queue,
                task_id,
                context_id,
                text=canned,
                data={
                    "citations": [],
                    "is_cold_start": False,
                    "used_fallback": False,
                    "retries_used": 0,
                    "smalltalk": True,
                },
            )
            await emit_completed(event_queue, task_id, context_id)
            return

        try:
            req = QueryRequest(
                question=question,
                subject_agent=filters.get("subject_agent"),
                max_citations=int(filters.get("max_citations", 10)),
                strict_mode=bool(filters.get("strict_mode", True)),
            )
        except Exception as e:
            await emit_failed(
                event_queue, task_id, context_id, f"invalid query filters: {e!s}"
            )
            return

        try:
            response = await execute_query(
                self.conn,
                self.narrative_provider,
                req,
                judge_provider=self.judge_provider or self.reflection_provider,
            )
        except ProviderUnavailableError as e:
            await emit_failed(
                event_queue,
                task_id,
                context_id,
                f"narrative provider unavailable: {e!s}",
            )
            return

        await emit_artifact(
            event_queue,
            task_id,
            context_id,
            text=response.answer,
            data={
                "citations": [c.model_dump() for c in response.citations],
                "is_cold_start": response.is_cold_start,
                "used_fallback": response.used_fallback,
                "retries_used": response.retries_used,
            },
        )
        await emit_completed(event_queue, task_id, context_id)
