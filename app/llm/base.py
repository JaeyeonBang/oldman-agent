"""LLM provider protocol + tier enum + request/response dataclasses.

Interface present in M1; real Anthropic / OpenRouter wiring lands in M2/M3.
LLMConfigError moved here in v1.0.1 so both providers share it cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class LLMConfigError(Exception):
    """LLM 제공자 설정 오류 (API 키 누락 등)."""


class LLMTier(StrEnum):
    CHEAP = "cheap"
    EXPENSIVE = "expensive"


@dataclass(frozen=True)
class LLMRequest:
    system: str
    prompt: str
    tier: LLMTier
    max_tokens: int = 1024
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    tier: LLMTier
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def complete(self, req: LLMRequest) -> LLMResponse: ...
