"""``execute_publish`` — A2A event ingest with rule blocklist + dedup.

::

    Publish flow (v2.5 race-safety):

      A2A message/send ──▶ pydantic validate ──▶ blocklist gate
        (oldman.intent='publish')                     │
                                                      ▼
                                          tokenize + Jaccard scan
                                                      │
                                                      ▼
                                        BEGIN TX ────────────────────┐
                                          INSERT events (L0)         │
                                          INSERT entities_episodic   │
                                          UPSERT entities_semantic   │  ← race
                                        COMMIT ──────────────────────┘    backstop
                                                      │                   ↓
                                                      ▼               UNIQUE(payload_hash)
                                              PublishResponse         IntegrityError
                                              status='stored'         (msg ⊃ 'payload_hash')
                                                                      → ROLLBACK
                                                                      → ExactHashDuplicateError

      Error mapping (raised, never HTTP):
        blocklist hit      → BlockedKindError
        Jaccard ≥ threshold → JaccardDuplicateError
        UNIQUE violation   → ExactHashDuplicateError  (race-safety backstop, T1+T4)
        any other DB error → ROLLBACK + re-raise (not a PublishError)

v2: ``execute_publish()`` core extracted as a callable so the A2A
AgentExecutor invokes the same path. Domain errors raise ``PublishError``
subclasses; the executor maps them to Task ack Messages.

v2.1: HTTP ``/publish`` route removed. Use JSON-RPC ``message/send`` with
``metadata.oldman.intent="publish"`` at ``POST /``.

v2.5: T4 regression test (`test_concurrent_same_hash_publish_yields_...`)
locks in: concurrent gather of two identical-payload publishes yields
exactly 1 success + 1 dedup error + 1 row in ``events``.
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
from app.credits.ledger import InsufficientFundsError
from app.credits.ledger import transfer as credits_transfer
from app.reflection.scheduler import maybe_run_reflection
from app.storage import entities as ent_store
from app.storage import events as evt_store
from app.storage.dedup import (
    BLOCKLISTED_KINDS,
    is_near_duplicate,
    payload_sha256,
    tokenize,
)
from app.trust.identity import verify_payload
from app.trust.payout import split_publish_payment
from app.trust.service import record_trust_event

OLDMAN_TREASURY_AGENT_ID = "oldman"

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


class InvalidSignatureError(PublishError):
    """v2 P0: seller_did/payload_signature 쌍이 불완전하거나 검증 실패."""

    def __init__(self) -> None:
        super().__init__("blocked", "invalid_signature")


class MissingSignatureError(PublishError):
    """v2 P0: require_signed_publish=True인데 무서명 publish."""

    def __init__(self) -> None:
        super().__init__("blocked", "missing_signature")


class OldmanInsufficientFundsError(PublishError):
    """v1.5 alpha: oldman's credits balance cannot cover publish_reward.

    Treats hypothesis-relevant info hard-failure (no event stored, no
    payment) per outside voice T2 — surfacing the signal beats silent
    degradation. ROLLBACK already runs via the publish TX wrapper.
    """

    def __init__(self) -> None:
        super().__init__("blocked", "oldman_insufficient_funds")


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

    # 1.5. seller 서명 검증 (v2 P0) — DID/서명 중 하나라도 오면 쌍 + 유효성 요구.
    # citation [↑eXX]가 "누가 판 정보인가"의 암호학적 증명을 갖게 하는 지점.
    if req.seller_did or req.payload_signature:
        if (
            not req.seller_did
            or not req.payload_signature
            or not verify_payload(req.seller_did, req.payload, req.payload_signature)
        ):
            raise InvalidSignatureError()
    elif settings.require_signed_publish:
        raise MissingSignatureError()

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

    # 5. transaction — pay-first, then persist with credits_tx_id baked
    # into the INSERT (DuckDB FK on entities_episodic.event_id blocks
    # post-insert UPDATEs to events).
    try:
        conn.execute("BEGIN")

        credits_tx_id: str | None = None
        if settings.payment_enabled and not settings.payment_kill_switch:
            try:
                if settings.royalty_enabled:
                    # v2 P2: 분할 지급 — listing fee 즉시 + 잔액 escrow
                    # (인용되면 royalty, 미인용 horizon 경과 시 소멸).
                    payout = split_publish_payment(
                        conn,
                        settings,
                        event_id=event_id,
                        seller_agent=req.source_agent,
                        now=ts,
                    )
                    credits_tx_id = payout.listing_fee_tx_id
                else:
                    credits_tx = credits_transfer(
                        conn,
                        from_agent=OLDMAN_TREASURY_AGENT_ID,
                        to_agent=req.source_agent,
                        amount=settings.publish_reward,
                        reason="publish_reward",
                        event_id=event_id,
                        starting_grant=settings.starting_grant,
                    )
                    credits_tx_id = credits_tx.tx_id
            except InsufficientFundsError as e:
                # Caught by outer `except Exception`, ROLLBACK, then
                # re-raised. Re-raise as a PublishError subclass so
                # executors map it like other publish blockers.
                raise OldmanInsufficientFundsError() from e

        evt_store.insert_event(
            conn,
            event_id=event_id,
            ts=ts,
            kind=req.event_kind,
            source_agent=req.source_agent,
            source_type=req.declared_source_type,
            payload=req.payload,
            payload_hash=p_hash,
            credits_tx_id=credits_tx_id,
            seller_did=req.seller_did,
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

    # 5.5. trust ledger — 정산된 매입만 reliability 증거가 된다 (거래-게이팅,
    # v2 P1/P2 glue). weight는 거래 건당 1.0 — 거래액 가중은 value-imbalance
    # 공격(소액 다수로 신뢰 축적)을 열므로 reliability 축에는 쓰지 않는다.
    # best-effort 부가 기록: 실패해도 committed publish를 뒤집지 않는다.
    if credits_tx_id is not None:
        with contextlib.suppress(Exception):
            record_trust_event(
                conn,
                agent_id=req.source_agent,
                criterion="reliability",
                positive=True,
                weight=1.0,
                cause="publish_settled",
                cause_ref=event_id,
                now=ts,
            )

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
