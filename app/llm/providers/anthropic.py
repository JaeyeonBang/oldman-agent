"""Anthropic Messages API provider — Phase 2.3.

prompt caching 활성화: system content에 cache_control={"type": "ephemeral"} 마커.
테스트 시 transport 주입으로 실제 HTTP 호출을 막는다.

환경변수:
    ANTHROPIC_API_KEY: API 키. 없으면 LLMConfigError 즉시 발생.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.llm.base import LLMConfigError, LLMRequest, LLMResponse

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

# Re-export for backward compatibility with existing test imports.
__all__ = ["AnthropicProvider", "LLMConfigError"]


@dataclass
class AnthropicProvider:
    """Anthropic Messages API 클라이언트.

    Args:
        api_key: Anthropic API 키. 빈 문자열 또는 None이면 LLMConfigError.
        model: 사용할 모델 이름.
        transport: httpx transport 주입 (테스트용). None이면 실제 HTTPS.
    """

    model: str = "claude-haiku-4-5-20251001"
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise LLMConfigError(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
                "환경변수 ANTHROPIC_API_KEY를 설정하거나 api_key 인자를 전달하세요."
            )

    @property
    def name(self) -> str:
        return "anthropic"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """Anthropic Messages API를 호출하여 LLMResponse를 반환한다.

        system 프롬프트에 cache_control={"type":"ephemeral"} 마커를 붙여
        프롬프트 캐싱을 활성화한다 (최소 1024 토큰 이상일 때 캐시 히트).

        Raises:
            httpx.HTTPStatusError: 4xx / 5xx 응답.
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _API_VERSION,
            "anthropic-beta": "prompt-caching-2024-07-31",
            "content-type": "application/json",
        }

        # system content를 cache_control 블록 형식으로 구성
        system_blocks = [
            {
                "type": "text",
                "text": req.system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        body = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "system": system_blocks,
            "messages": [
                {"role": "user", "content": req.prompt},
            ],
        }

        kwargs: dict[str, Any] = {}
        if self.transport is not None:
            kwargs["transport"] = self.transport

        async with httpx.AsyncClient(**kwargs) as client:
            response = await client.post(
                _API_URL,
                headers=headers,
                json=body,
                timeout=60.0,
            )

        response.raise_for_status()
        data = response.json()

        text = data["content"][0]["text"]
        usage = data.get("usage", {})
        response_model = data.get("model", self.model)

        return LLMResponse(
            text=text,
            model=response_model,
            tier=req.tier,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
