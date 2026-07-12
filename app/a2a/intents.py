"""Intent extraction helpers for oldman_agent A2A message dispatch.

Operates on **proto** ``a2a.types.a2a_pb2.Message`` (the SDK delivers proto
types to executor.execute via the request handler, not the compat pydantic
types).

The A2A spec leaves semantic intent to the agent. oldman_agent uses
``message.metadata["oldman.intent"]`` with values "publish" | "query".

Heuristic fallback (when metadata key absent):
  - TextPart present + no DataPart → treat as ``query``
  - DataPart-only or ambiguous → return None (executor emits failed)
"""

from __future__ import annotations

from typing import Any

from a2a.types.a2a_pb2 import Message
from google.protobuf.json_format import MessageToDict  # type: ignore[import-untyped]

INTENT_PUBLISH = "publish"
INTENT_QUERY = "query"
INTENT_REPUTATION = "reputation"  # v2 P4 — "그 에이전트 어때?" 평판 조회
INTENT_METADATA_KEY = "oldman.intent"


def extract_intent(message: Message) -> str | None:
    """Return the oldman intent from ``message.metadata``, or None."""
    if not message.HasField("metadata"):
        return None
    metadata_fields = message.metadata.fields
    if INTENT_METADATA_KEY not in metadata_fields:
        return None
    value = metadata_fields[INTENT_METADATA_KEY]
    if value.WhichOneof("kind") == "string_value":
        return str(value.string_value)
    return None


def heuristic_intent(message: Message) -> str | None:
    """Heuristic fallback when intent metadata is absent.

    - TextPart present, no DataPart → "query"
    - Otherwise → None (executor will emit failed with helpful error)
    """
    has_text = bool(get_text(message).strip())
    has_data = _has_data_part(message)
    if has_text and not has_data:
        return INTENT_QUERY
    return None


def get_data_part(message: Message) -> dict[str, Any] | None:
    """Return the first DataPart's data as a plain Python dict, or None."""
    for part in message.parts:
        if part.HasField("data"):
            # part.data is a google.protobuf.Value; convert via json_format
            result: dict[str, Any] = MessageToDict(part.data)
            return result
    return None


def get_text(message: Message) -> str:
    """Return concatenated text from all text Parts."""
    texts = [part.text for part in message.parts if part.HasField("text")]
    return "\n".join(texts)


# ── private ──────────────────────────────────────────────────────────────────


def _has_data_part(message: Message) -> bool:
    return any(part.HasField("data") for part in message.parts)
