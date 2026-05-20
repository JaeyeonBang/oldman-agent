"""Phase 6.4 — A2A v0.2 compliance contract test.

Parses the live /agent-card response through the a2a-sdk pydantic type and
asserts no validation errors. Falls back to a vendored type if the SDK import
fails (per plan Decision 6.7).

SDK used: a2a.compat.v0_3.types.AgentCard (pydantic v2, A2A v0.2 public spec).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


def _get_a2a_agent_card_type():  # type: ignore[no-untyped-def]
    """Return the A2A AgentCard type: SDK first, vendored fallback."""
    try:
        from a2a.compat.v0_3.types import AgentCard as A2AAgentCard
        return A2AAgentCard
    except ImportError:
        # vendored fallback (created if SDK install failed in Phase 6.2)
        from app.api.a2a_spec import AgentCard as A2AAgentCard  # type: ignore[import]
        return A2AAgentCard


@pytest.mark.asyncio
async def test_agent_card_validates_against_a2a_v0_2_schema(async_client: AsyncClient) -> None:
    """GET /agent-card must parse cleanly through the A2A v0.2 schema type."""
    resp = await async_client.get("/agent-card")
    assert resp.status_code == 200
    raw = resp.json()

    A2AAgentCard = _get_a2a_agent_card_type()

    # Must NOT raise — full A2A v0.2 validation
    validated = (
        A2AAgentCard.model_validate(raw)
        if hasattr(A2AAgentCard, "model_validate")
        else A2AAgentCard(**raw)
    )
    assert validated is not None

    # vendor extension survives in the raw dict (SDK strips it; that's fine)
    assert "x-oldman" in raw
    assert raw["x-oldman"]["persona"] == "꼰대 정보통"
    assert raw["x-oldman"]["protocol_version_target"] == "0.3"  # v2 bump


@pytest.mark.asyncio
async def test_agent_card_a2a_required_fields_present(async_client: AsyncClient) -> None:
    """All A2A v0.2 required fields must be in the response."""
    resp = await async_client.get("/agent-card")
    raw = resp.json()

    required = ("name", "description", "url", "version", "capabilities",
                 "defaultInputModes", "defaultOutputModes", "skills")
    for field in required:
        assert field in raw, f"A2A v0.2 required field missing: {field}"


@pytest.mark.asyncio
async def test_agent_card_skills_have_required_a2a_fields(async_client: AsyncClient) -> None:
    """Each skill must have id, name, description, tags (A2A v0.2 required)."""
    resp = await async_client.get("/agent-card")
    raw = resp.json()

    for skill in raw["skills"]:
        for field in ("id", "name", "description", "tags"):
            assert field in skill, f"skill '{skill.get('id')}' missing A2A field: {field}"
        assert isinstance(skill["tags"], list)
        assert len(skill["tags"]) >= 1
