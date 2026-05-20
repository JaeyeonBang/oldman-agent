"""Unit tests for app.a2a.intents — Phase 8.1 TDD."""

from __future__ import annotations

from a2a.types.a2a_pb2 import Message, Part
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Value

from app.a2a.intents import (
    INTENT_METADATA_KEY,
    INTENT_PUBLISH,
    INTENT_QUERY,
    extract_intent,
    get_data_part,
    get_text,
    heuristic_intent,
)


def _make_message(
    text_parts: list[str] | None = None,
    data_parts: list[dict] | None = None,
    metadata: dict | None = None,
) -> Message:
    m = Message(message_id="test-id", role="ROLE_USER")
    for t in text_parts or []:
        m.parts.append(Part(text=t))
    for d in data_parts or []:
        v = Value()
        ParseDict(d, v)
        m.parts.append(Part(data=v))
    if metadata:
        for k, val in metadata.items():
            m.metadata.fields[k].string_value = val
    return m


def test_extract_intent_returns_publish_when_metadata_set():
    msg = _make_message(metadata={INTENT_METADATA_KEY: INTENT_PUBLISH})
    assert extract_intent(msg) == INTENT_PUBLISH


def test_extract_intent_returns_query_when_metadata_set():
    msg = _make_message(metadata={INTENT_METADATA_KEY: INTENT_QUERY})
    assert extract_intent(msg) == INTENT_QUERY


def test_extract_intent_returns_none_when_metadata_absent():
    msg = _make_message()
    assert extract_intent(msg) is None


def test_extract_intent_returns_none_when_key_not_in_metadata():
    msg = _make_message(metadata={"other.key": "value"})
    assert extract_intent(msg) is None


def test_heuristic_falls_back_to_query_on_text_only():
    msg = _make_message(text_parts=["어떤 에이전트가 활발했나요?"])
    assert heuristic_intent(msg) == INTENT_QUERY


def test_heuristic_returns_none_when_data_present_but_no_intent():
    msg = _make_message(data_parts=[{"event_kind": "chat"}])
    assert heuristic_intent(msg) is None


def test_heuristic_returns_none_when_parts_empty():
    msg = _make_message()
    assert heuristic_intent(msg) is None


def test_get_data_part_extracts_dict():
    payload = {"event_kind": "chat", "source_agent": "agent_a"}
    msg = _make_message(data_parts=[payload])
    result = get_data_part(msg)
    assert result is not None
    assert result["event_kind"] == "chat"
    assert result["source_agent"] == "agent_a"


def test_get_data_part_returns_none_when_no_data_part():
    msg = _make_message(text_parts=["hello"])
    assert get_data_part(msg) is None


def test_get_text_extracts_concatenated_text():
    msg = _make_message(text_parts=["hello", "world"])
    result = get_text(msg)
    assert "hello" in result
    assert "world" in result
