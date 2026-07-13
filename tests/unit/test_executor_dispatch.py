"""Unit tests for OldmanAgentExecutor dispatch — Phase 8.3 TDD.

Uses proto types (a2a.types.a2a_pb2) directly since the SDK delivers proto
to executor.execute at runtime. Manually constructs RequestContext bypassing
the full request handler chain.
"""

from __future__ import annotations

import uuid
from pathlib import Path

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
from app.a2a.intents import INTENT_METADATA_KEY, INTENT_PUBLISH, INTENT_QUERY
from app.config import Settings
from app.llm.providers.mock import MockProvider
from app.storage.db import apply_migrations, get_conn


class FakeQueue:
    def __init__(self) -> None:
        self.events: list = []

    async def enqueue_event(self, event: object) -> None:
        self.events.append(event)

    async def close(self) -> None:
        pass


def _make_context(message: Message) -> RequestContext:
    """Wrap a proto Message in a SendMessageRequest + RequestContext."""
    req = SendMessageRequest(message=message)
    server_ctx = ServerCallContext(user=UnauthenticatedUser())
    return RequestContext(call_context=server_ctx, request=req)


@pytest.fixture()
def executor(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    conn = get_conn(str(db_path))
    apply_migrations(conn)
    settings = Settings(
        db_path=str(db_path), jaccard_window=50, jaccard_threshold=0.9
    )
    narrative = MockProvider(mode="narrative")
    reflection = MockProvider(mode="reflection")
    judge = MockProvider(mode="judge")
    yield OldmanAgentExecutor(
        conn=conn,
        settings=settings,
        narrative_provider=narrative,
        reflection_provider=reflection,
        judge_provider=judge,
    )
    conn.close()


def _publish_msg(**overrides) -> Message:
    data = {
        "event_kind": "chat",
        "source_agent": "agent_alice",
        "observed_agent": "agent_bob",
        "declared_source_type": "third_party",
        "payload": {"text": "hello world"},
    }
    data.update(overrides)
    m = Message(message_id=str(uuid.uuid4()), role="ROLE_USER")
    m.metadata.fields[INTENT_METADATA_KEY].string_value = INTENT_PUBLISH
    v = Value()
    ParseDict(data, v)
    m.parts.append(Part(data=v))
    return m


def _query_msg(question: str = "agent_alice가 최근 어떤 모습을 보였나요?") -> Message:
    m = Message(message_id=str(uuid.uuid4()), role="ROLE_USER")
    m.metadata.fields[INTENT_METADATA_KEY].string_value = INTENT_QUERY
    m.parts.append(Part(text=question))
    v = Value()
    ParseDict({"subject_agent": "agent_alice", "strict_mode": False}, v)
    m.parts.append(Part(data=v))
    return m


def _states(events: list) -> list:
    """Return states from initial Task + subsequent TaskStatusUpdateEvent in order."""
    states = []
    for e in events:
        if isinstance(e, (Task, TaskStatusUpdateEvent)):
            states.append(e.status.state)
    return states


def _artifacts(events: list) -> list[TaskArtifactUpdateEvent]:
    return [e for e in events if isinstance(e, TaskArtifactUpdateEvent)]


@pytest.mark.asyncio
async def test_settlement_generic_error_rolls_back_transaction(executor, monkeypatch):
    """C3 회귀 — 정산 중 InsufficientFundsError가 *아닌* 예외가 나도 트랜잭션이
    반드시 롤백되어, 공유 단일 writer 커넥션이 mid-transaction으로 남지 않아야
    한다. 롤백을 안 하면 다음 요청의 BEGIN이 전부 실패해 서비스가 브릭된다.
    """
    import app.a2a.executor as ex_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("boom during settlement")

    monkeypatch.setattr(ex_mod, "credits_transfer", _boom)
    q = FakeQueue()
    with pytest.raises(RuntimeError):
        await executor._charge_querier_or_fallback(
            question="q",
            subject_agent="agent_alice",
            querier_agent="agent_carol",
            task_id="t1",
            context_id="c1",
            event_queue=q,
        )
    # 커넥션이 열린 트랜잭션에 갇혀 있지 않아야 한다 — 새 BEGIN이 성공해야 함.
    executor.conn.execute("BEGIN")
    executor.conn.execute("COMMIT")


@pytest.mark.asyncio
async def test_execute_unknown_intent_emits_failed(executor):
    m = Message(message_id="m1", role="ROLE_USER")
    v = Value()
    ParseDict({"foo": "bar"}, v)
    m.parts.append(Part(data=v))
    q = FakeQueue()
    await executor.execute(_make_context(m), q)
    states = _states(q.events)
    assert states == [TaskState.TASK_STATE_FAILED]


@pytest.mark.asyncio
async def test_execute_publish_intent_persists_and_emits_completed(executor):
    msg = _publish_msg()
    q = FakeQueue()
    await executor.execute(_make_context(msg), q)
    states = _states(q.events)
    assert states == [
        TaskState.TASK_STATE_SUBMITTED,
        TaskState.TASK_STATE_COMPLETED,
    ]
    arts = _artifacts(q.events)
    assert len(arts) == 1
    data_dict = MessageToDict(arts[0].artifact.parts[1].data)
    assert data_dict["status"] == "stored"
    assert data_dict["event_id"]


@pytest.mark.asyncio
async def test_execute_publish_blocklisted_kind_emits_blocked_artifact(executor):
    msg = _publish_msg(event_kind="heartbeat")
    q = FakeQueue()
    await executor.execute(_make_context(msg), q)
    states = _states(q.events)
    assert states == [
        TaskState.TASK_STATE_SUBMITTED,
        TaskState.TASK_STATE_COMPLETED,
    ]
    arts = _artifacts(q.events)
    data_dict = MessageToDict(arts[0].artifact.parts[1].data)
    assert data_dict["status"] == "blocked"
    assert data_dict["reason"] == "blocklisted_kind"


@pytest.mark.asyncio
async def test_execute_publish_invalid_payload_emits_blocked(executor):
    m = Message(message_id="m1", role="ROLE_USER")
    m.metadata.fields[INTENT_METADATA_KEY].string_value = INTENT_PUBLISH
    v = Value()
    ParseDict({"event_kind": "chat", "source_agent": "a"}, v)  # missing fields
    m.parts.append(Part(data=v))
    q = FakeQueue()
    await executor.execute(_make_context(m), q)
    states = _states(q.events)
    assert states == [
        TaskState.TASK_STATE_SUBMITTED,
        TaskState.TASK_STATE_COMPLETED,
    ]
    arts = _artifacts(q.events)
    data_dict = MessageToDict(arts[0].artifact.parts[1].data)
    assert data_dict["status"] == "blocked"


@pytest.mark.asyncio
async def test_execute_query_intent_emits_lifecycle_submitted_working_completed(executor):
    msg = _query_msg()
    q = FakeQueue()
    await executor.execute(_make_context(msg), q)
    states = _states(q.events)
    assert states == [
        TaskState.TASK_STATE_SUBMITTED,
        TaskState.TASK_STATE_WORKING,
        TaskState.TASK_STATE_COMPLETED,
    ]
    arts = _artifacts(q.events)
    assert len(arts) == 1
    text_part = arts[0].artifact.parts[0]
    data_part = arts[0].artifact.parts[1]
    assert text_part.HasField("text")
    assert text_part.text
    data_dict = MessageToDict(data_part.data)
    assert "citations" in data_dict
    assert "isColdStart" in data_dict or "is_cold_start" in data_dict
    assert "usedFallback" in data_dict or "used_fallback" in data_dict


@pytest.mark.asyncio
async def test_execute_heuristic_text_only_treats_as_query(executor):
    m = Message(message_id="m1", role="ROLE_USER")
    m.parts.append(Part(text="society 동향이 궁금합니다"))
    q = FakeQueue()
    await executor.execute(_make_context(m), q)
    states = _states(q.events)
    assert states == [
        TaskState.TASK_STATE_SUBMITTED,
        TaskState.TASK_STATE_WORKING,
        TaskState.TASK_STATE_COMPLETED,
    ]


@pytest.mark.asyncio
async def test_execute_publish_missing_datapart_emits_failed(executor):
    m = Message(message_id="m1", role="ROLE_USER")
    m.metadata.fields[INTENT_METADATA_KEY].string_value = INTENT_PUBLISH
    m.parts.append(Part(text="이건 텍스트뿐"))
    q = FakeQueue()
    await executor.execute(_make_context(m), q)
    states = _states(q.events)
    assert TaskState.TASK_STATE_SUBMITTED in states
    assert TaskState.TASK_STATE_FAILED in states


# ── v2 P4: reputation intent ──────────────────────────────────────────────────


def _reputation_msg(subject: str = "ghost_bot") -> Message:
    m = Message(message_id=str(uuid.uuid4()), role="ROLE_USER")
    m.metadata.fields[INTENT_METADATA_KEY].string_value = "reputation"
    v = Value()
    ParseDict({"subject_agent": subject}, v)
    m.parts.append(Part(data=v))
    return m


@pytest.mark.asyncio
async def test_execute_reputation_intent_unknown_subject(executor):
    """모르는 에이전트 → '미지' 평판 narrative + completed."""
    q = FakeQueue()
    await executor.execute(_make_context(_reputation_msg()), q)
    states = _states(q.events)
    assert states[-1] == TaskState.TASK_STATE_COMPLETED
    arts = _artifacts(q.events)
    assert len(arts) == 1
    text = "".join(
        p.text for p in arts[0].artifact.parts if p.HasField("text")
    )
    assert "모르는 이름" in text


@pytest.mark.asyncio
async def test_execute_reputation_intent_without_subject_fails(executor):
    m = Message(message_id=str(uuid.uuid4()), role="ROLE_USER")
    m.metadata.fields[INTENT_METADATA_KEY].string_value = "reputation"
    q = FakeQueue()
    await executor.execute(_make_context(m), q)
    states = _states(q.events)
    assert states[-1] == TaskState.TASK_STATE_FAILED
