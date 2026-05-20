"""OpenRouter provider — Phase 6.0 (v1.0.1 plan debt resolution).

OpenAI-compatible /chat/completions 엔드포인트를 사용한다.
캐시 제어 마커 없음 — OpenRouter passthrough가 Anthropic cache_control을 신뢰성 있게
전달하지 않으므로 생략한다 (Decision 6.1).

환경변수:
    OPENROUTER_API_KEY: API 키. 없으면 LLMConfigError 즉시 발생.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.llm.base import LLMConfigError, LLMRequest, LLMResponse

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_HTTP_REFERER = "https://github.com/oldman-agent"
_X_TITLE = "oldman_agent"


@dataclass
class OpenRouterProvider:
    """OpenRouter /chat/completions 클라이언트 (OpenAI-compatible).

    Args:
        api_key: OpenRouter API 키. 빈 문자열 또는 None이면 LLMConfigError.
        model: 사용할 모델 이름 (OpenRouter 형식: "provider/model").
        transport: httpx transport 주입 (테스트용). None이면 실제 HTTPS.
    """

    model: str = "anthropic/claude-opus-4-7"
    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise LLMConfigError(
                "OPENROUTER_API_KEY가 설정되지 않았습니다. "
                "환경변수 OPENROUTER_API_KEY를 설정하거나 api_key 인자를 전달하세요."
            )

    @property
    def name(self) -> str:
        return "openrouter"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """OpenRouter /chat/completions API를 호출하여 LLMResponse를 반환한다.

        OpenAI-compatible 메시지 형식: system + user 두 개의 별도 메시지.
        cache_control 마커는 포함하지 않는다 (Decision 6.1).

        Raises:
            httpx.HTTPStatusError: 4xx / 5xx 응답.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": _HTTP_REFERER,
            "X-Title": _X_TITLE,
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "messages": [
                {"role": "system", "content": req.system},
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

        # v1.0.5 defensive: reasoning models (e.g. deepseek-v4-flash, o1, r1)
        # return message.content=None until the full reasoning trace fits in
        # max_tokens. Surface a clear error rather than TypeError on subscript.
        choices = data.get("choices") or []
        if not choices:
            raise ValueError(
                f"OpenRouter: response has no choices (model={self.model}, "
                f"id={data.get('id')})"
            )
        message = choices[0].get("message") or {}
        text = message.get("content")
        if text is None:
            reasoning = message.get("reasoning")
            finish = choices[0].get("finish_reason")
            hint = (
                " (모델이 reasoning model로 보임 — max_tokens 부족이거나 "
                "non-reasoning 변종으로 교체 필요)"
                if reasoning
                else ""
            )
            raise ValueError(
                f"OpenRouter: message.content=None (model={self.model}, "
                f"finish_reason={finish}){hint}"
            )

        usage = data.get("usage", {})
        response_model = data.get("model", self.model)

        return LLMResponse(
            text=text,
            model=response_model,
            tier=req.tier,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
