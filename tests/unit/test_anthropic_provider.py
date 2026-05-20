"""Phase 2.3 — RED tests: AnthropicProvider real HTTP implementation.

실제 API 호출 없음. httpx.MockTransport으로 모킹.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.llm.base import LLMRequest, LLMResponse, LLMTier
from app.llm.providers.anthropic import AnthropicProvider, LLMConfigError

# ── mock transport helpers ────────────────────────────────────────────────────

def _make_anthropic_response(
    text: str = "테스트 응답",
    model: str = "claude-haiku-4-5-20251001",
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> dict[str, Any]:
    """Anthropic Messages API 성공 응답 형식."""
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": model,
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
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

class TestAnthropicProviderCacheControl:
    """시스템 프롬프트에 cache_control 마커가 포함되는지 확인."""

    @pytest.mark.asyncio
    async def test_anthropic_provider_sends_cache_control_on_system(self) -> None:
        transport = _MockTransport(_make_anthropic_response())
        provider = AnthropicProvider(api_key="sk-test-key", transport=transport)

        req = LLMRequest(
            system="시스템 프롬프트",
            prompt="사용자 메시지",
            tier=LLMTier.CHEAP,
        )
        await provider.complete(req)

        assert transport.last_request is not None
        body = json.loads(transport.last_request.content)

        # system이 list[dict] 형식이어야 함 (cache_control 블록 지원)
        assert isinstance(body["system"], list)
        assert len(body["system"]) >= 1
        # 마지막 블록에 cache_control 있어야 함
        last_block = body["system"][-1]
        assert "cache_control" in last_block
        assert last_block["cache_control"] == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_anthropic_provider_sends_correct_api_version_header(self) -> None:
        transport = _MockTransport(_make_anthropic_response())
        provider = AnthropicProvider(api_key="sk-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP)
        await provider.complete(req)

        assert transport.last_request is not None
        assert transport.last_request.headers["anthropic-version"] == "2023-06-01"
        assert transport.last_request.headers["x-api-key"] == "sk-test-key"


class TestAnthropicProviderResponseParsing:
    """응답 파싱 + 토큰 카운트 확인."""

    @pytest.mark.asyncio
    async def test_anthropic_provider_parses_response_text_and_token_counts(
        self,
    ) -> None:
        body = _make_anthropic_response(
            text="분석 결과입니다",
            input_tokens=150,
            output_tokens=30,
        )
        transport = _MockTransport(body)
        provider = AnthropicProvider(api_key="sk-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP)
        resp = await provider.complete(req)

        assert isinstance(resp, LLMResponse)
        assert resp.text == "분석 결과입니다"
        assert resp.input_tokens == 150
        assert resp.output_tokens == 30
        assert resp.tier == LLMTier.CHEAP

    @pytest.mark.asyncio
    async def test_anthropic_provider_uses_model_from_response(self) -> None:
        body = _make_anthropic_response(model="claude-haiku-4-5-20251001")
        transport = _MockTransport(body)
        provider = AnthropicProvider(api_key="sk-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP)
        resp = await provider.complete(req)
        assert resp.model == "claude-haiku-4-5-20251001"


class TestAnthropicProviderErrors:
    """에러 케이스: API key 없음, 5xx."""

    def test_anthropic_provider_missing_api_key_raises_config_error(self) -> None:
        with pytest.raises(LLMConfigError, match="ANTHROPIC_API_KEY"):
            AnthropicProvider(api_key="")

    def test_anthropic_provider_none_api_key_raises_config_error(self) -> None:
        # api_key를 환경변수에서 읽을 때 None이 들어오는 경우
        with pytest.raises(LLMConfigError, match="ANTHROPIC_API_KEY"):
            AnthropicProvider(api_key=None)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_anthropic_provider_5xx_raises(self) -> None:
        transport = _MockTransport(
            {"error": {"type": "server_error", "message": "Internal Server Error"}},
            status_code=500,
        )
        provider = AnthropicProvider(api_key="sk-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.complete(req)

    @pytest.mark.asyncio
    async def test_anthropic_provider_4xx_raises(self) -> None:
        transport = _MockTransport(
            {"error": {"type": "authentication_error", "message": "Invalid API Key"}},
            status_code=401,
        )
        provider = AnthropicProvider(api_key="sk-test-key", transport=transport)

        req = LLMRequest(system="sys", prompt="user", tier=LLMTier.CHEAP)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.complete(req)


class TestAnthropicProviderMaxTokens:
    """max_tokens가 요청 본문에 전달되는지 확인."""

    @pytest.mark.asyncio
    async def test_anthropic_provider_respects_max_tokens(self) -> None:
        transport = _MockTransport(_make_anthropic_response())
        provider = AnthropicProvider(api_key="sk-test-key", transport=transport)

        req = LLMRequest(
            system="sys", prompt="user", tier=LLMTier.CHEAP, max_tokens=512
        )
        await provider.complete(req)

        assert transport.last_request is not None
        body = json.loads(transport.last_request.content)
        assert body["max_tokens"] == 512
