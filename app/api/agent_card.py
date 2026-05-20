"""``GET /agent-card`` — A2A v0.2 card with ``x-oldman`` vendor extension.

v2 changes:
- ``url`` resolved from ``OLDMAN_BASE_URL`` env (default ``http://localhost:8080``).
- ``capabilities.streaming = True`` (we now support ``message/stream``).
- Skill descriptions document the ``metadata.oldman.intent`` contract.

The same dict is served at ``/.well-known/agent-card.json`` (A2A SDK standard
discovery path) by ``app/a2a/routes.py``.
"""

from __future__ import annotations

import os
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


def _resolve_base_url() -> str:
    return os.environ.get("OLDMAN_BASE_URL", "http://localhost:8080")


def build_agent_card() -> AgentCard:
    """Build the canonical AgentCard (env-driven; called per app startup)."""
    return AgentCard(
        name="oldman_agent",
        description=(
            "꼰대 정보통 — A2A 메타-기록자. 에이전트들의 정보·일화를 수집·축적·구조화하고 "
            "꼰대 페르소나로 사회 history narrative를 제공한다."
        ),
        url=_resolve_base_url(),
        version=__version__,
        capabilities=AgentCardCapabilities(  # type: ignore[call-arg]
            streaming=True,
            push_notifications=False,
            state_transition_history=False,
        ),
        default_input_modes=["application/json"],
        default_output_modes=["application/json", "text/plain"],
        skills=[
            AgentCardSkill(
                id="publish_event",
                name="publish",
                description=(
                    "A2A 이벤트 ingest — 규칙 blocklist + Jaccard dedup + 트랜잭션 저장. "
                    "호출법: message/send with metadata.oldman.intent='publish' "
                    "and a DataPart containing event_kind/source_agent/observed_agent/payload."
                ),
                tags=["publish"],
            ),
            AgentCardSkill(
                id="narrative_query",
                name="narrative_query",
                description=(
                    "꼰대 페르소나 기반 내러티브 쿼리 — inline citation 강제, "
                    "LLM judge hallucination 검증. "
                    "호출법: message/send 또는 message/stream with "
                    "metadata.oldman.intent='query', TextPart for the question, "
                    "optional DataPart for filters (subject_agent, max_citations, strict_mode)."
                ),
                tags=["query", "narrative"],
            ),
        ],
        x_oldman=AgentCardOldmanExtension(
            persona="꼰대 정보통",
            citation_required=True,
            protocol_version_target="0.3",
        ),
    )


def card_to_well_known_dict(card: AgentCard) -> dict[str, Any]:
    """Serialize AgentCard to the wire JSON shape."""
    return card.model_dump(by_alias=True)


@router.get("/agent-card")
async def agent_card() -> dict[str, Any]:
    return card_to_well_known_dict(build_agent_card())
