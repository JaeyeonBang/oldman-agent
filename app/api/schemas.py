"""pydantic v2 schemas for /publish, /query, and /agent-card.

Strict + ``extra='forbid'`` on requests; payload dict is opaque (lenient).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["self", "third_party", "mutual"]
PublishStatus = Literal["stored", "deduplicated", "blocked"]


class PublishRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    event_kind: str = Field(min_length=1)
    source_agent: str = Field(min_length=1)
    observed_agent: str | None = None
    declared_source_type: SourceType
    payload: dict[str, Any]
    ts: datetime | None = None


class PublishResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PublishStatus
    event_id: str | None = None
    reason: str | None = None


class AgentCardSkill(BaseModel):
    """A2A v0.2 skill entry."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    name: str
    description: str
    tags: list[str]
    examples: list[str] | None = None
    input_modes: list[str] | None = Field(default=None, alias="inputModes")
    output_modes: list[str] | None = Field(default=None, alias="outputModes")


class AgentCardCapabilities(BaseModel):
    """A2A v0.2 capabilities block.

    Old ``publish``/``query`` booleans are gone — capability is now expressed
    via skill tags (``publish_event`` → tags=[\"publish\"], etc.).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    streaming: bool = False
    push_notifications: bool = Field(default=False, alias="pushNotifications")
    state_transition_history: bool = Field(default=False, alias="stateTransitionHistory")


class AgentCardOldmanExtension(BaseModel):
    """``x-oldman`` vendor extension on the A2A agent card."""

    model_config = ConfigDict(extra="forbid")

    persona: str
    citation_required: bool
    protocol_version_target: str = "0.2"


class Citation(BaseModel):
    """쿼리 응답에 포함된 단일 인용 항목."""

    model_config = ConfigDict(extra="forbid")

    short_id: str
    """event_id 앞 8자리 hex."""

    event_id: str | None = None
    """DB에서 확인된 전체 event_id (optional — 검증 완료 시 채워짐)."""


class QueryRequest(BaseModel):
    """POST /query 요청 스키마."""

    model_config = ConfigDict(strict=True, extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    subject_agent: str | None = None
    max_citations: int = Field(default=10, ge=1, le=100)
    strict_mode: bool = True
    """True(기본)이면 LLM judge 기반 내용 검증. False이면 존재 검증만 수행."""


class QueryResponse(BaseModel):
    """POST /query 응답 스키마."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[Citation]
    is_cold_start: bool
    retries_used: int
    used_fallback: bool = False


class AgentCard(BaseModel):
    """A2A v0.2 agent card + ``x-oldman`` vendor extension.

    Breaking change from pre-v1.0.1:
    - ``protocol_version`` removed from top level (now in ``x-oldman.protocol_version_target``)
    - ``capabilities.publish``/``.query`` removed (expressed via skill tags)
    - ``url``, ``defaultInputModes``, ``defaultOutputModes`` added
    - Two skills: ``publish_event`` + ``narrative_query``

    Serialised with camelCase aliases per A2A v0.2 spec.
    ``x-oldman`` alias bridges the hyphenated vendor extension key.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    description: str
    url: str
    version: str
    provider: dict[str, str] | None = None
    documentation_url: str | None = Field(default=None, alias="documentationUrl")
    capabilities: AgentCardCapabilities
    default_input_modes: list[str] = Field(alias="defaultInputModes")
    default_output_modes: list[str] = Field(alias="defaultOutputModes")
    skills: list[AgentCardSkill]
    security: list[dict[str, list[str]]] | None = None
    x_oldman: AgentCardOldmanExtension = Field(alias="x-oldman")
