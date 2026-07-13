"""Phase 1.3 RED: pydantic schema invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    AgentCard,
    AgentCardCapabilities,
    AgentCardOldmanExtension,
    AgentCardSkill,
    PublishRequest,
)


def test_publish_request_accepts_minimal_payload() -> None:
    req = PublishRequest(
        event_kind="chat",
        source_agent="agent_alice",
        declared_source_type="self",
        payload={"text": "안녕"},
    )
    assert req.observed_agent is None
    assert req.ts is None
    assert req.payload == {"text": "안녕"}


def test_publish_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        PublishRequest(
            event_kind="chat",
            source_agent="a",
            declared_source_type="self",
            payload={},
            stray="nope",  # type: ignore[call-arg]
        )


def test_publish_request_rejects_invalid_source_type() -> None:
    with pytest.raises(ValidationError):
        PublishRequest(
            event_kind="chat",
            source_agent="a",
            declared_source_type="bogus",  # type: ignore[arg-type]
            payload={},
        )


def test_publish_request_rejects_empty_event_kind() -> None:
    with pytest.raises(ValidationError):
        PublishRequest(
            event_kind="",
            source_agent="a",
            declared_source_type="self",
            payload={},
        )


def test_publish_request_rejects_oversized_seller_did() -> None:
    """H2 회귀 — did:key는 ~56자. 무제한이면 base58 O(n^2) 디코드로 단일
    writer 프로세스를 수십 초 블록시키는 DoS. 길이 상한으로 조기 거부."""
    with pytest.raises(ValidationError):
        PublishRequest(
            event_kind="chat",
            source_agent="a",
            declared_source_type="self",
            payload={},
            seller_did="z" * 100_000,
            payload_signature="c2ln",
        )


def test_publish_request_rejects_oversized_signature() -> None:
    """H2 회귀 — base64(64B ed25519 sig)=88자. 무제한 금지."""
    with pytest.raises(ValidationError):
        PublishRequest(
            event_kind="chat",
            source_agent="a",
            declared_source_type="self",
            payload={},
            seller_did="did:key:z6Mk",
            payload_signature="A" * 100_000,
        )


def test_agent_card_alias_serialization() -> None:
    # v1.0.1: A2A v0.2 shape — url required, capabilities has streaming/push/state fields
    card = AgentCard(
        name="oldman_agent",
        description="꼰대 정보통",
        url="http://localhost:8080",
        version="0.1.0-m1",
        capabilities=AgentCardCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json", "text/plain"],
        skills=[AgentCardSkill(id="publish_event", name="publish", description="L0 ingest", tags=["publish"])],
        x_oldman=AgentCardOldmanExtension(persona="꼰대 정보통", citation_required=True),  # type: ignore[call-arg]
    )
    dumped = card.model_dump(by_alias=True)
    assert "x-oldman" in dumped
    assert dumped["x-oldman"]["persona"] == "꼰대 정보통"
    assert "x_oldman" not in dumped
    # v0.2 camelCase aliases
    assert "defaultInputModes" in dumped
    assert "defaultOutputModes" in dumped
    assert "pushNotifications" in dumped["capabilities"]
