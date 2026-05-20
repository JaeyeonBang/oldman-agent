"""Phase 6.0 — RED tests: OpenRouterProvider real HTTP implementation.

실제 API 호출 없음. httpx.MockTransport으로 모킹.
OpenRouter의 OpenAI-compatible /chat/completions 엔드포인트를 검증한다.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.llm.base import LLMConfigError, LLMRequest, LLMResponse, LLMTier
from app.llm.providers.openrouter import OpenRouterProvider

# ── mock transport helpers ────────────────────────────────────────────────────

def _make_openrouter_response(
    text: str = "테스트 응답",
    model: str = "anthropic/claude-opus-4-7",
    prompt_tokens: int = 100,
    completion_tokens: int = 20,
) -> dict[str, Any]:
    """OpenRouter /chat/completions 성공 응답 형식 (OpenAI-compatible)."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


class _MockTransport(httpx.AsyncBaseTransport):
    """단일 응답을 반환하는 AsyncBaseTransport 구현체 (테스트 전용)."""

    def __init__(self, response_body: dict[str, Any], status_code: int = 200) -> None:
        self._response_body = response_body
        self._status_code = status_code
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return httpx.Response(
            status_code=self._status_code,
            headers={"content-type": "application/json"},
            content=json.dumps(self._response_body).encode(),
        )


# ── tests ─────────────────────────────────────────────────────────────────────

class TestOpenRouterAuth:
    """Bearer 인증 + 엔드포인트 확인."""

    @pytest.mark.asyncio
    async def test_openrouter_sends_bearer_auth_and_endpoint(self) -> None:
        transport = _MockTransport(_make_openrouter_response())
        provider = OpenRouterProvider(api_key="or-test-key", transport=transport)

        req = LLMRequest(system="시스템 프롬프트", prompt="사용자 메시지", tier=LLMTier.CHEAP)
        await provider.complete(req)

        assert transport.last_request is not None
        assert "openrouter.ai" in str(transport.last_request.url)
        assert "/chat/completions" in str(transport.last_request.url)
        assert transport.last_request.headers["authorization"] == "Bearer or-test-key"

    @pytest.mark.asyncio
    async def test_openrouter_sends_referer_and_title_headers(self) -> None:
        transport = _MockTransport(_make_openrouter_response())
        provider = OpenRouterProvider(api_key="or-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP)
        await provider.complete(req)

        assert transport.last_request is not None
        headers = transport.last_request.headers
        assert "http-referer" in headers or "HTTP-Referer" in {k: v for k, v in headers.items()}
        assert "x-title" in headers or "X-Title" in {k: v for k, v in headers.items()}


class TestOpenRouterResponseParsing:
    """choices 형식 응답 파싱 + 토큰 카운트."""

    @pytest.mark.asyncio
    async def test_openrouter_parses_choices_response_format(self) -> None:
        body = _make_openrouter_response(
            text="분석 결과입니다",
            prompt_tokens=150,
            completion_tokens=30,
        )
        transport = _MockTransport(body)
        provider = OpenRouterProvider(api_key="or-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP)
        resp = await provider.complete(req)

        assert isinstance(resp, LLMResponse)
        assert resp.text == "분석 결과입니다"
        assert resp.input_tokens == 150
        assert resp.output_tokens == 30
        assert resp.tier == LLMTier.CHEAP


class TestOpenRouterErrors:
    """에러 케이스: API key 없음, 5xx."""

    def test_openrouter_missing_api_key_raises_config_error(self) -> None:
        with pytest.raises(LLMConfigError, match="OPENROUTER_API_KEY"):
            OpenRouterProvider(api_key="")

    @pytest.mark.asyncio
    async def test_openrouter_5xx_raises(self) -> None:
        transport = _MockTransport(
            {"error": {"message": "Internal Server Error"}},
            status_code=500,
        )
        provider = OpenRouterProvider(api_key="or-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.complete(req)


class TestOpenRouterMaxTokens:
    """max_tokens가 요청 본문에 전달되는지 확인."""

    @pytest.mark.asyncio
    async def test_openrouter_respects_max_tokens(self) -> None:
        transport = _MockTransport(_make_openrouter_response())
        provider = OpenRouterProvider(api_key="or-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP, max_tokens=512)
        await provider.complete(req)

        assert transport.last_request is not None
        body = json.loads(transport.last_request.content)
        assert body["max_tokens"] == 512


class TestOpenRouterNoCacheControl:
    """OpenRouter 요청 본문에 cache_control 마커가 없어야 한다."""

    @pytest.mark.asyncio
    async def test_openrouter_no_cache_control_markers_in_body(self) -> None:
        transport = _MockTransport(_make_openrouter_response())
        provider = OpenRouterProvider(api_key="or-test-key", transport=transport)

        req = LLMRequest(system="긴 시스템 프롬프트", prompt="user", tier=LLMTier.CHEAP)
        await provider.complete(req)

        assert transport.last_request is not None
        body_str = transport.last_request.content.decode()
        assert "cache_control" not in body_str
        assert "ephemeral" not in body_str

        # messages는 system + user 두 개여야 한다
        body = json.loads(body_str)
        assert "messages" in body
        roles = [m["role"] for m in body["messages"]]
        assert roles == ["system", "user"]
