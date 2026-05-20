"""Task lifecycle event helpers for OldmanAgentExecutor.

Wraps A2A SDK proto event types so the executor can express Task state
transitions without touching SDK internals directly. All functions are async
and accept any object that has ``enqueue_event(event) -> Awaitable`` (matches
EventQueue).

Uses **proto** event types from ``a2a.types.a2a_pb2`` (SDK runtime types).
"""

from __future__ import annotations

import uuid

from a2a.types.a2a_pb2 import (
    Artifact,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from google.protobuf.json_format import ParseDict  # type: ignore[import-untyped]
from google.protobuf.struct_pb2 import Value  # type: ignore[import-untyped]


def _make_value(data: dict) -> Value:  # type: ignore[type-arg]
    """Convert a plain Python dict into a protobuf Value (struct_value)."""
    v = Value()
    ParseDict(data, v)
    return v


async def emit_submitted(queue: object, task_id: str, context_id: str) -> None:
    """Emit the initial Task (with submitted status).

    SDK invariant: the executor must enqueue a Task object BEFORE any
    TaskStatusUpdateEvent. We satisfy that by emitting the Task here with
    state=submitted (no separate status event needed at this stage).
    """
    await queue.enqueue_event(  # type: ignore[attr-defined]
        Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
        )
    )


async def emit_working(
    queue: object,
    task_id: str,
    context_id: str,
    message_hint: str | None = None,
) -> None:
    """Emit TaskStatusUpdateEvent(working)."""
    await queue.enqueue_event(  # type: ignore[attr-defined]
        TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
        )
    )


async def emit_artifact(
    queue: object,
    task_id: str,
    context_id: str,
    *,
    text: str,
    data: dict,  # type: ignore[type-arg]
) -> None:
    """Emit TaskArtifactUpdateEvent with TextPart + DataPart."""
    parts = [
        Part(text=text),
        Part(data=_make_value(data)),
    ]
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        parts=parts,
    )
    await queue.enqueue_event(  # type: ignore[attr-defined]
        TaskArtifactUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            artifact=artifact,
            last_chunk=True,
        )
    )


async def emit_completed(queue: object, task_id: str, context_id: str) -> None:
    """Emit TaskStatusUpdateEvent(completed)."""
    await queue.enqueue_event(  # type: ignore[attr-defined]
        TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        )
    )


async def emit_failed(
    queue: object, task_id: str, context_id: str, error_message: str
) -> None:
    """Emit TaskStatusUpdateEvent(failed)."""
    await queue.enqueue_event(  # type: ignore[attr-defined]
        TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_FAILED),
        )
    )


async def emit_canceled(queue: object, task_id: str, context_id: str) -> None:
    """Emit TaskStatusUpdateEvent(canceled)."""
    await queue.enqueue_event(  # type: ignore[attr-defined]
        TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_CANCELED),
        )
    )
