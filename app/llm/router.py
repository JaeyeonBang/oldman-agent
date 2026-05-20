"""LLM tier router. Reads ``config/llm.yaml`` and dispatches by ``LLMTier``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTier
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.mock import MockProvider
from app.llm.providers.openrouter import OpenRouterProvider

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "llm.yaml"


def build_provider(provider_name: str, model: str | None = None) -> LLMProvider:
    if provider_name == "mock":
        return MockProvider(model=model or "mock-1")
    if provider_name == "anthropic":
        return AnthropicProvider(model=model or "claude-haiku-4-5-20251001")
    if provider_name == "openrouter":
        return OpenRouterProvider(model=model or "anthropic/claude-opus-4-7")
    raise ValueError(f"unknown provider: {provider_name}")


def _load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _DEFAULT_CONFIG_PATH
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class LLMRouter:
    def __init__(self, providers: dict[LLMTier, LLMProvider]) -> None:
        self._providers = providers

    @classmethod
    def from_config(cls, path: Path | None = None) -> LLMRouter:
        cfg = _load_config(path)
        providers: dict[LLMTier, LLMProvider] = {}
        for tier in LLMTier:
            tier_cfg = cfg.get(tier.value, {})
            providers[tier] = build_provider(
                provider_name=tier_cfg.get("provider", "mock"),
                model=tier_cfg.get("model"),
            )
        return cls(providers)

    def provider_for(self, tier: LLMTier) -> LLMProvider:
        return self._providers[tier]

    async def complete(self, req: LLMRequest) -> LLMResponse:
        return await self.provider_for(req.tier).complete(req)
