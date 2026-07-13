"""개선 B — 전체 신뢰 사이클 통합 테스트 (executor 디스패치 경유).

서명 publish(분할 지급 + escrow) → 유료 query(mock narrative 인용 → royalty
해제 + 풀 수수료) → reputation intent → 회계 감사(자산 보존 invariant).
unit 테스트가 함수 단위로 검증한 조각들이 실제 A2A 디스패치 경로를 통째로
통과하는지 확인한다.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from a2a.auth.user import UnauthenticatedUser
from a2a.server.agent_execution.context import RequestContext
from a2a.server.context import ServerCallContext
from a2a.types.a2a_pb2 import (
    Message,
    Part,
    SendMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Value

from app.a2a.executor import OldmanAgentExecutor
from app.a2a.intents import INTENT_METADATA_KEY
from app.config import Settings
from app.credits.audit import audit_credits
from app.credits.ledger import get_balance
from app.llm.providers.mock import MockProvider
from app.storage.db import apply_migrations, get_conn
from app.trust.identity import generate_identity, sign_payload
from app.trust.refund_pool import VILLAGE_POOL_AGENT_ID


class FakeQueue:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def enqueue_event(self, event: object) -> None:
        self.events.append(event)

    async def close(self) -> None:
        pass


def _ctx(message: Message) -> RequestContext:
    req = SendMessageRequest(message=message)
    return RequestContext(
        call_context=ServerCallContext(user=UnauthenticatedUser()), request=req
    )


def _msg(intent: str, *, text: str | None = None, data: dict | None = None) -> Message:
    m = Message(message_id=str(uuid.uuid4()), role="ROLE_USER")
    m.metadata.fields[INTENT_METADATA_KEY].string_value = intent
    if text is not None:
        m.parts.append(Part(text=text))
    if data is not None:
        v = Value()
        ParseDict(data, v)
        m.parts.append(Part(data=v))
    return m


def _final_state(events: list[Any]) -> Any:
    states = [
        e.status.state
        for e in events
        if isinstance(e, (Task, TaskStatusUpdateEvent))
    ]
    return states[-1]


def _artifact_text_and_data(events: list[Any]) -> tuple[str, dict[str, Any]]:
    arts = [e for e in events if isinstance(e, TaskArtifactUpdateEvent)]
    assert len(arts) == 1
    text = "".join(p.text for p in arts[0].artifact.parts if p.HasField("text"))
    data: dict[str, Any] = {}
    for p in arts[0].artifact.parts:
        if p.HasField("data"):
            data = MessageToDict(p.data)
    return text, data


@pytest.mark.asyncio
async def test_full_trust_cycle_through_executor(tmp_path: Path) -> None:
    conn = get_conn(str(tmp_path / "cycle.duckdb"))
    apply_migrations(conn)
    settings = Settings(
        db_path=str(tmp_path / "cycle.duckdb"),
        jaccard_window=50,
        jaccard_threshold=0.9,
        payment_enabled=True,
        royalty_enabled=True,
        publish_reward=5,
        query_price=3,
        refund_pool_fee=1,
        starting_grant=100,
    )
    executor = OldmanAgentExecutor(
        conn=conn,
        settings=settings,
        narrative_provider=MockProvider(mode="narrative"),
        reflection_provider=None,
        judge_provider=MockProvider(mode="judge"),
    )
    seller = generate_identity()

    # ① 서명 publish — 분할 지급 (listing fee 1 즉시 + escrow 4)
    payload = {"text": "kimbot이 마을 데이터셋을 공개했다"}
    q1 = FakeQueue()
    await executor.execute(
        _ctx(
            _msg(
                "publish",
                data={
                    "event_kind": "anecdote",
                    "source_agent": "kimbot",
                    "observed_agent": "kimbot",
                    "declared_source_type": "third_party",
                    "payload": payload,
                    "seller_did": seller.did,
                    "payload_signature": sign_payload(
                        seller.seed_hex, payload, "kimbot"
                    ),
                },
            )
        ),
        q1,
    )
    assert _final_state(q1.events) == TaskState.TASK_STATE_COMPLETED
    assert get_balance(conn, "kimbot") == 101  # grant 100 + listing fee 1
    escrow = conn.execute(
        "SELECT seller_agent, amount, status, event_id FROM royalty_escrows"
    ).fetchone()
    assert escrow is not None
    assert escrow[0] == "kimbot"
    assert (escrow[1], escrow[2]) == (4, "open")
    trust_row = conn.execute(
        "SELECT cause FROM trust_events WHERE agent_id='kimbot'"
    ).fetchone()
    assert trust_row == ("publish_settled",)
    seller_did_row = conn.execute("SELECT seller_did FROM events").fetchone()
    assert seller_did_row == (seller.did,)

    # cold start 해제 — is_cold는 "이벤트 ≥1 AND reflection ≥1" (reflection 시드)
    conn.execute(
        "INSERT INTO reflections (reflection_id, ts, scope, subject, text, "
        "event_range_start, event_range_end, source_event_ids) "
        "VALUES (?, CURRENT_TIMESTAMP, 'agent', 'kimbot', 'kimbot 관찰 요약', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '[]')",
        [str(uuid.uuid4())],
    )

    # ② 유료 query — mock narrative가 저장된 event를 인용 → royalty 해제
    q2 = FakeQueue()
    await executor.execute(
        _ctx(
            _msg(
                "query",
                text="kimbot 요즘 어떤가?",
                data={
                    "subject_agent": "kimbot",
                    "strict_mode": False,
                    "querier_agent": "querier_zed",
                },
            )
        ),
        q2,
    )
    assert _final_state(q2.events) == TaskState.TASK_STATE_COMPLETED
    _text2, data2 = _artifact_text_and_data(q2.events)
    assert data2.get("citations"), "mock narrative가 인용을 생성해야 함"
    royalties = data2.get("royalties", [])
    assert any(r.get("status") == "paid" for r in royalties), royalties
    assert get_balance(conn, "kimbot") == 105  # +royalty 4
    assert get_balance(conn, "querier_zed") == 97  # -query_price 3
    assert get_balance(conn, VILLAGE_POOL_AGENT_ID) == 101  # +pool fee 1
    invoice = conn.execute("SELECT status FROM invoices").fetchone()
    assert invoice == ("settled",)

    # ③ reputation intent — 주관적 labeler narrative (유료)
    q3 = FakeQueue()
    await executor.execute(
        _ctx(
            _msg(
                "reputation",
                data={"subject_agent": "kimbot", "querier_agent": "querier_zed"},
            )
        ),
        q3,
    )
    assert _final_state(q3.events) == TaskState.TASK_STATE_COMPLETED
    text3, data3 = _artifact_text_and_data(q3.events)
    assert "내가 보기엔 kimbot" in text3
    assert data3["state"] == "provisional"  # 매입 1건 — 아직 "미지"

    # ④ 회계 감사 — 전체 사이클 후 자산 보존
    report = audit_credits(conn)
    assert report.balanced is True
    assert report.issues == []
    conn.close()
