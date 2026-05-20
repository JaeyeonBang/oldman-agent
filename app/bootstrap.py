"""Provider wiring for oldman_agent — Phase 6.1 (v1.0.1 config-driven bootstrap).

``configure_providers(app)`` is called once inside ``create_app()`` to inject
LLM provider instances into ``app.state``.

Config: ``config/llm.yaml`` is authoritative per tier (cheap / expensive / judge).
Env vars are credentials only — ANTHROPIC_API_KEY, OPENROUTER_API_KEY.

If a provider is configured but its API key is absent, falls back to MockProvider
with a WARNING log. Unknown provider names raise ValueError immediately.

Tests override ``_load_llm_config`` to avoid disk reads.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

from app.llm.providers.mock import MockProvider

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm.yaml"

# Tier name in yaml → app.state attribute name
_TIER_ATTR = {
    "cheap": "reflection_provider",
    "judge": "judge_provider",
    "expensive": "narrative_provider",
}


def _load_llm_config() -> dict[str, Any]:
    """Load config/llm.yaml and return as dict. Separated for test patching."""
    with _CONFIG_PATH.open() as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


def _build_provider(
    tier: str,
    provider_name: str,
    model: str,
) -> Any:
    """Instantiate the correct provider for *tier*, or mock with a warning on missing key."""
    if provider_name == "mock":
        # Phase 7.1: wire mode per tier so smart mock works without API keys
        _TIER_MODE = {
            "cheap": "reflection",
            "expensive": "narrative",
            "judge": "judge",
        }
        mode = _TIER_MODE.get(tier, "bare")
        return MockProvider(mode=mode)

    if provider_name == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning(
                "ANTHROPIC_API_KEY 미설정 — tier '%s' provider를 MockProvider로 대체합니다.",
                tier,
            )
            return MockProvider()
        from app.llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=model, api_key=api_key)

    if provider_name == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning(
                "OPENROUTER_API_KEY 미설정 — tier '%s' provider를 MockProvider로 대체합니다.",
                tier,
            )
            return MockProvider()
        # v1.0.5: config의 model이 비어있거나 "openrouter-default"이면
        # OPENROUTER_DEFAULT_MODEL env로 폴백. 둘 다 없으면 하드코딩 기본값.
        resolved_model = model
        if not resolved_model or resolved_model == "openrouter-default":
            resolved_model = os.environ.get(
                "OPENROUTER_DEFAULT_MODEL", "anthropic/claude-opus-4-7"
            )
        from app.llm.providers.openrouter import OpenRouterProvider
        return OpenRouterProvider(model=resolved_model, api_key=api_key)

    raise ValueError(
        f"알 수 없는 provider 이름: '{provider_name}' (tier='{tier}'). "
        "config/llm.yaml에서 mock|anthropic|openrouter 중 하나를 사용하세요."
    )


def configure_providers(app: FastAPI) -> None:
    """``app.state``에 reflection / judge / narrative provider를 주입한다.

    config/llm.yaml을 읽어 각 tier의 provider + model을 결정한다.
    API 키 부재 시 MockProvider로 fallback (WARNING 로그).
    Unknown provider name → ValueError.

    Notes:
        - 이미 ``app.state``에 값이 있어도 덮어쓴다 (idempotent).
        - 테스트는 ``create_app()`` 반환 후 ``app.state.x = custom`` 으로 교체 가능.
    """
    config = _load_llm_config()

    for yaml_tier, state_attr in _TIER_ATTR.items():
        tier_cfg = config.get(yaml_tier, {})
        provider_name: str = tier_cfg.get("provider", "mock")
        model: str = tier_cfg.get("model", "mock-stub")
        provider = _build_provider(yaml_tier, provider_name, model)
        setattr(app.state, state_attr, provider)
