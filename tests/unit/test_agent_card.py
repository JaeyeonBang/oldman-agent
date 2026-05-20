"""Phase 1.5 / 6.3 — /agent-card endpoint tests (A2A v0.2 shape).

Phase 6.3 breaking changes:
- capabilities: {streaming, push_notifications, state_transition_history} instead of {publish, query}
- top-level `url` field added
- top-level `protocol_version` removed (moved to x-oldman.protocol_version_target)
- skills: both publish_event and narrative_query present with tags
- defaultInputModes / defaultOutputModes present
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_agent_card_returns_200_and_required_fields(async_client: AsyncClient) -> None:
    resp = await async_client.get("/agent-card")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("name", "version", "url", "description", "capabilities", "skills",
                "defaultInputModes", "defaultOutputModes"):
        assert key in body, f"missing required key: {key}"


@pytest.mark.asyncio
async def test_agent_card_capabilities_a2a_v02_shape(async_client: AsyncClient) -> None:
    """capabilities must have streaming/push_notifications/state_transition_history — not publish/query."""
    body = (await async_client.get("/agent-card")).json()
    caps = body["capabilities"]
    # v0.2 fields present
    assert "streaming" in caps
    assert "pushNotifications" in caps
    assert "stateTransitionHistory" in caps
    # old fields must NOT be present
    assert "publish" not in caps, "legacy 'publish' field must be removed"
    assert "query" not in caps, "legacy 'query' field must be removed"


@pytest.mark.asyncio
async def test_agent_card_lists_publish_skill(async_client: AsyncClient) -> None:
    body = (await async_client.get("/agent-card")).json()
    skill_ids = {s["id"] for s in body["skills"]}
    assert "publish_event" in skill_ids


@pytest.mark.asyncio
async def test_agent_card_x_oldman_extension(async_client: AsyncClient) -> None:
    body = (await async_client.get("/agent-card")).json()
    assert "x-oldman" in body
    assert body["x-oldman"]["persona"] == "꼰대 정보통"
    assert body["x-oldman"]["citation_required"] is True


# ── Phase 6.3 new tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_card_no_legacy_top_level_protocol_version(async_client: AsyncClient) -> None:
    """top-level protocol_version must be gone; it lives in x-oldman.protocol_version_target."""
    body = (await async_client.get("/agent-card")).json()
    assert "protocol_version" not in body, (
        "protocol_version must be removed from top level (now in x-oldman.protocol_version_target)"
    )
    assert "protocol_version_target" in body["x-oldman"], (
        "protocol_version_target must exist in x-oldman vendor extension"
    )


@pytest.mark.asyncio
async def test_agent_card_skills_include_publish_and_narrative_query_tags(
    async_client: AsyncClient,
) -> None:
    """Both skills present with correct tags."""
    body = (await async_client.get("/agent-card")).json()
    skills = {s["id"]: s for s in body["skills"]}

    assert "publish_event" in skills, "publish_event skill required"
    assert "narrative_query" in skills, "narrative_query skill required"

    assert "publish" in skills["publish_event"]["tags"]
    assert "query" in skills["narrative_query"]["tags"]
    assert "narrative" in skills["narrative_query"]["tags"]


@pytest.mark.asyncio
async def test_agent_card_default_input_output_modes_present(async_client: AsyncClient) -> None:
    """defaultInputModes and defaultOutputModes must be present with correct values."""
    body = (await async_client.get("/agent-card")).json()
    assert body["defaultInputModes"] == ["application/json"]
    assert "application/json" in body["defaultOutputModes"]
    assert "text/plain" in body["defaultOutputModes"]
