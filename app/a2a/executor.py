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
import contextlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types.a2a_pb2 import Message

from app.a2a.intents import (
    INTENT_PUBLISH,
    INTENT_QUERY,
    INTENT_REPUTATION,
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
    OLDMAN_TREASURY_AGENT_ID,
    PublishError,
    execute_publish,
)
from app.api.query import ProviderUnavailableError, execute_query
from app.api.schemas import PublishRequest, QueryRequest
from app.config import Settings
from app.credits.ledger import InsufficientFundsError
from app.credits.ledger import transfer as credits_transfer
from app.narrative.smalltalk import match_smalltalk
from app.storage.invoices import (
    insert_pending_invoice,
    mark_invoice_invalidated,
    mark_invoice_settled,
)
from app.trust.payout import release_royalties_for_citations
from app.trust.report import build_reputation_report

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
        elif intent == INTENT_REPUTATION:
            await self._dispatch_reputation(message, task_id, context_id, event_queue)
        else:
            await emit_failed(
                event_queue,
                task_id,
                context_id,
                (
                    "missing 'oldman.intent' metadata. "
                    "Set message.metadata['oldman.intent'] to 'publish', 'query' "
                    "or 'reputation'. "
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
        except PublishError as e:
            # BlockedKindError / JaccardDuplicateError / ExactHashDuplicateError
            # / OldmanInsufficientFundsError all surface the same shape.
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

        # v1.5 alpha — pay-to-query (PRD D5: invoice + settle separate TXs).
        # Skip entirely when disabled or kill-switch tripped.
        settled_invoice_id: str | None = None
        if self.settings.payment_enabled and not self.settings.payment_kill_switch:
            handled, settled_invoice_id = await self._charge_querier_or_fallback(
                question=question,
                subject_agent=req.subject_agent,
                querier_agent=filters.get("querier_agent"),
                task_id=task_id,
                context_id=context_id,
                event_queue=event_queue,
            )
            if handled:
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

        # v2 P2 — 정산된 query의 citation은 escrow royalty를 해제한다
        # ("인용되면 지급"). 실패해도 이미 계산된 응답 전달을 막지 않는다.
        royalties: list[dict[str, Any]] | None = None
        if settled_invoice_id is not None and self.settings.royalty_enabled:
            try:
                releases = release_royalties_for_citations(
                    self.conn,
                    self.settings,
                    citation_event_ids=[
                        c.event_id for c in response.citations if c.event_id
                    ],
                    invoice_id=settled_invoice_id,
                    now=datetime.now(UTC),
                )
                royalties = [
                    {
                        "event_id": r.event_id,
                        "seller_agent": r.seller_agent,
                        "amount": r.amount,
                        "status": r.status,
                    }
                    for r in releases
                ]
            except Exception:
                _LOG.exception("royalty release failed (invoice=%s)", settled_invoice_id)
                royalties = [{"status": "error"}]

        artifact_data: dict[str, Any] = {
            "citations": [c.model_dump() for c in response.citations],
            "is_cold_start": response.is_cold_start,
            "used_fallback": response.used_fallback,
            "retries_used": response.retries_used,
        }
        if royalties is not None:
            artifact_data["royalties"] = royalties

        await emit_artifact(
            event_queue,
            task_id,
            context_id,
            text=response.answer,
            data=artifact_data,
        )
        await emit_completed(event_queue, task_id, context_id)

    # ── v2 P4: reputation intent ────────────────────────────────────────

    async def _dispatch_reputation(
        self,
        message: Message,
        task_id: str,
        context_id: str,
        event_queue: EventQueue,
    ) -> None:
        """"그 에이전트 어때?" — trust ledger 기반 주관적 평판 narrative.

        template v0 (LLM 미사용). 발화는 주관적 labeler 프레이밍 + 전 주장
        trust_events citation. 유료 (payment_enabled 시 query와 동일 과금).
        """
        await emit_submitted(event_queue, task_id, context_id)
        filters = get_data_part(message) or {}
        subject = filters.get("subject_agent") or get_text(message).strip()
        if not subject or not isinstance(subject, str):
            await emit_failed(
                event_queue,
                task_id,
                context_id,
                "reputation intent requires subject_agent (DataPart) or a TextPart",
            )
            return
        await emit_working(event_queue, task_id, context_id)

        if self.settings.payment_enabled and not self.settings.payment_kill_switch:
            handled, _ = await self._charge_querier_or_fallback(
                question=f"reputation:{subject}",
                subject_agent=subject,
                querier_agent=filters.get("querier_agent"),
                task_id=task_id,
                context_id=context_id,
                event_queue=event_queue,
            )
            if handled:
                return

        report = build_reputation_report(self.conn, subject_agent=subject)
        await emit_artifact(
            event_queue,
            task_id,
            context_id,
            text=report.text,
            data={
                "subject_agent": report.subject_agent,
                "state": report.state,
                "violation_count": report.violation_count,
                "citations": [
                    {
                        "short_id": c.short_id,
                        "trust_event_id": c.trust_event_id,
                        "cause": c.cause,
                    }
                    for c in report.citations
                ],
            },
        )
        await emit_completed(event_queue, task_id, context_id)

    # ── v1.5 alpha: pay-to-query ────────────────────────────────────────

    async def _charge_querier_or_fallback(
        self,
        *,
        question: str,
        subject_agent: str | None,
        querier_agent: Any,
        task_id: str,
        context_id: str,
        event_queue: EventQueue,
    ) -> tuple[bool, str | None]:
        """Issue invoice + attempt ledger settlement.

        Returns ``(handled, settled_invoice_id)`` — handled=True면 fallback
        응답이 이미 emit됨 (caller must return). 정산 성공 시 invoice id를
        돌려줘 citation royalty 해제(v2 P2)의 원인 ref로 쓴다.

        Per PRD D5, invoice and settlement are written in *separate*
        transactions so the audit row survives settlement failure.
        """
        if not querier_agent or not isinstance(querier_agent, str):
            await self._emit_insufficient_funds_fallback(
                event_queue,
                task_id,
                context_id,
                reason="missing_querier_agent",
            )
            return True, None

        invoice_id = str(uuid.uuid4())
        expiry = datetime.now(UTC) + timedelta(
            seconds=self.settings.invoice_ttl_seconds
        )

        # Step 1: invoice issuance (separate TX).
        self.conn.execute("BEGIN")
        insert_pending_invoice(
            self.conn,
            invoice_id=invoice_id,
            query=question,
            subject_agent=subject_agent,
            intent_expiry=expiry,
        )
        self.conn.execute("COMMIT")

        # Step 2: settlement (separate TX so invoice row survives rejection).
        try:
            self.conn.execute("BEGIN")
            credits_tx = credits_transfer(
                self.conn,
                from_agent=querier_agent,
                to_agent=OLDMAN_TREASURY_AGENT_ID,
                amount=self.settings.query_price,
                reason="query_price",
                invoice_id=invoice_id,
                starting_grant=self.settings.starting_grant,
            )
            mark_invoice_settled(
                self.conn,
                invoice_id,
                credits_tx.tx_id,
                settled_at=datetime.now(UTC),
            )
            self.conn.execute("COMMIT")
        except InsufficientFundsError:
            with contextlib.suppress(duckdb.Error):
                self.conn.execute("ROLLBACK")
            # Fresh TX so the invalidated marker persists.
            self.conn.execute("BEGIN")
            mark_invoice_invalidated(self.conn, invoice_id)
            self.conn.execute("COMMIT")
            await self._emit_insufficient_funds_fallback(
                event_queue,
                task_id,
                context_id,
                reason="querier_insufficient_funds",
            )
            return True, None

        return False, invoice_id

    async def _emit_insufficient_funds_fallback(
        self,
        event_queue: EventQueue,
        task_id: str,
        context_id: str,
        *,
        reason: str,
    ) -> None:
        """Canned 토큰 부족 narrative + complete the task. No citations
        (no real evidence pipeline ran) and used_fallback=True flags
        the off-path response for the admin dashboard."""
        await emit_artifact(
            event_queue,
            task_id,
            context_id,
            text="토큰이 부족하시구먼, 다음에 또 들르시게.",
            data={
                "citations": [],
                "is_cold_start": False,
                "used_fallback": True,
                "retries_used": 0,
                "payment_status": "invalidated",
                "payment_reason": reason,
            },
        )
        await emit_completed(event_queue, task_id, context_id)
