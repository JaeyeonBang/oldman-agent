"""Phase 1.7 RED: LLM router skeleton."""

from __future__ import annotations

import pytest

from app.llm.base import LLMRequest, LLMTier
from app.llm.providers.anthropic import AnthropicProvider, LLMConfigError
from app.llm.providers.mock import MockProvider
from app.llm.providers.openrouter import OpenRouterProvider
from app.llm.router import LLMRouter, build_provider


def test_build_provider_mock() -> None:
    p = build_provider("mock")
    assert isinstance(p, MockProvider)
    assert p.name == "mock"


def test_build_provider_anthropic_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """M2: AnthropicProvider는 실제 구현이며 API 키가 있으면 생성된다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-build")
    p = build_provider("anthropic")
    assert isinstance(p, AnthropicProvider)
    assert p.name == "anthropic"


def test_build_provider_openrouter_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    # v1.0.1: OpenRouterProvider is real — requires OPENROUTER_API_KEY
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-build")
    p = build_provider("openrouter")
    assert isinstance(p, OpenRouterProvider)
    assert p.name == "openrouter"


def test_build_provider_unknown_raises() -> None:
    with pytest.raises(ValueError):
        build_provider("bogus")


def test_anthropic_provider_missing_api_key_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M2: ANTHROPIC_API_KEY 미설정 시 LLMConfigError를 던진다."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()


def test_openrouter_missing_key_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # v1.0.1: OpenRouterProvider is real — raises LLMConfigError when key absent
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider()


@pytest.mark.asyncio
async def test_router_routes_cheap_to_mock() -> None:
    router = LLMRouter.from_config()
    resp = await router.complete(LLMRequest(system="", prompt="x", tier=LLMTier.CHEAP))
    assert resp.text == "[mock]"
    assert resp.tier == LLMTier.CHEAP


@pytest.mark.asyncio
async def test_router_routes_expensive_to_mock() -> None:
    router = LLMRouter.from_config()
    resp = await router.complete(LLMRequest(system="", prompt="x", tier=LLMTier.EXPENSIVE))
    assert resp.text == "[mock]"
    assert resp.tier == LLMTier.EXPENSIVE
