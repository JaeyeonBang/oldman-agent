"""Unit tests for app.a2a.task_emitter — Phase 8.2 TDD."""

from __future__ import annotations

import pytest
from a2a.types.a2a_pb2 import (
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from google.protobuf.json_format import MessageToDict

from app.a2a.task_emitter import (
    emit_artifact,
    emit_canceled,
    emit_completed,
    emit_failed,
    emit_submitted,
    emit_working,
)

TASK_ID = "task-abc"
CONTEXT_ID = "ctx-xyz"


class FakeQueue:
    """Collects enqueued events for assertion."""

    def __init__(self) -> None:
        self.events: list = []

    async def enqueue_event(self, event: object) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_emit_submitted_enqueues_initial_task():
    """emit_submitted emits an initial Task (SDK invariant: Task before any status events)."""
    q = FakeQueue()
    await emit_submitted(q, TASK_ID, CONTEXT_ID)
    assert len(q.events) == 1
    evt = q.events[0]
    assert isinstance(evt, Task)
    assert evt.status.state == TaskState.TASK_STATE_SUBMITTED
    assert evt.id == TASK_ID
    assert evt.context_id == CONTEXT_ID


@pytest.mark.asyncio
async def test_emit_working_enqueues_working_status():
    q = FakeQueue()
    await emit_working(q, TASK_ID, CONTEXT_ID)
    assert len(q.events) == 1
    evt = q.events[0]
    assert isinstance(evt, TaskStatusUpdateEvent)
    assert evt.status.state == TaskState.TASK_STATE_WORKING


@pytest.mark.asyncio
async def test_emit_artifact_enqueues_artifact_event_with_text_and_data():
    q = FakeQueue()
    await emit_artifact(q, TASK_ID, CONTEXT_ID, text="안녕하세요", data={"key": "val"})
    assert len(q.events) == 1
    evt = q.events[0]
    assert isinstance(evt, TaskArtifactUpdateEvent)
    assert evt.task_id == TASK_ID
    assert len(evt.artifact.parts) == 2
    text_part = evt.artifact.parts[0]
    data_part = evt.artifact.parts[1]
    assert text_part.HasField("text")
    assert text_part.text == "안녕하세요"
    assert data_part.HasField("data")
    data_dict = MessageToDict(data_part.data)
    assert data_dict["key"] == "val"


@pytest.mark.asyncio
async def test_emit_completed_enqueues_completed_status():
    q = FakeQueue()
    await emit_completed(q, TASK_ID, CONTEXT_ID)
    assert len(q.events) == 1
    evt = q.events[0]
    assert isinstance(evt, TaskStatusUpdateEvent)
    assert evt.status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.asyncio
async def test_emit_failed_enqueues_failed_status():
    q = FakeQueue()
    await emit_failed(q, TASK_ID, CONTEXT_ID, "some error")
    assert len(q.events) == 1
    evt = q.events[0]
    assert isinstance(evt, TaskStatusUpdateEvent)
    assert evt.status.state == TaskState.TASK_STATE_FAILED


@pytest.mark.asyncio
async def test_emit_canceled_enqueues_canceled_status():
    q = FakeQueue()
    await emit_canceled(q, TASK_ID, CONTEXT_ID)
    assert len(q.events) == 1
    evt = q.events[0]
    assert isinstance(evt, TaskStatusUpdateEvent)
    assert evt.status.state == TaskState.TASK_STATE_CANCELED
