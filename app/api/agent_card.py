"""``GET /agent-card`` — A2A v0.2 card with ``x-oldman`` vendor extension.

Breaking change from pre-v1.0.1:
- capabilities shape changed: streaming/push_notifications/state_transition_history
- Two skills: publish_event (tags=["publish"]) + narrative_query (tags=["query","narrative"])
- url now top-level; protocol_version moved to x-oldman.protocol_version_target
- defaultInputModes + defaultOutputModes added
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import __version__
from app.api.schemas import (
    AgentCard,
    AgentCardCapabilities,
    AgentCardOldmanExtension,
    AgentCardSkill,
)

router = APIRouter()

# TODO: resolve url at runtime (from env/config) for deployed instances
_AGENT_URL = "http://localhost:8080"

_CARD = AgentCard(
    name="oldman_agent",
    description="꼰대 정보통 — A2A 메타-기록자. 에이전트들의 정보·일화를 수집·축적·구조화하고 꼰대 페르소나로 사회 history narrative를 제공한다.",
    url=_AGENT_URL,
    version=__version__,
    capabilities=AgentCardCapabilities(  # type: ignore[call-arg]
        streaming=False,
        push_notifications=False,
        state_transition_history=False,
    ),
    default_input_modes=["application/json"],
    default_output_modes=["application/json", "text/plain"],
    skills=[
        AgentCardSkill(
            id="publish_event",
            name="publish",
            description="A2A 이벤트 ingest — 규칙 blocklist + Jaccard dedup + 트랜잭션 저장.",
            tags=["publish"],
        ),
        AgentCardSkill(
            id="narrative_query",
            name="narrative_query",
            description="꼰대 페르소나 기반 내러티브 쿼리 — inline citation 강제, LLM judge hallucination 검증.",
            tags=["query", "narrative"],
        ),
    ],
    x_oldman=AgentCardOldmanExtension(
        persona="꼰대 정보통",
        citation_required=True,
        protocol_version_target="0.2",
    ),
)


@router.get("/agent-card")
async def agent_card() -> dict[str, Any]:
    return _CARD.model_dump(by_alias=True)
