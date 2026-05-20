"""Phase 5.0 / 6.1 — tests for app/bootstrap.py provider wiring.

Phase 6.1 adds config-driven bootstrap: config/llm.yaml is authoritative per tier.
Existing tests updated to use a mock-only yaml (the default); new tests cover
anthropic/openrouter/mixed/fallback/unknown scenarios via patched yaml content.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI

from app.bootstrap import configure_providers
from app.llm.providers.mock import MockProvider

# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_yaml(cheap: str, expensive: str, judge: str) -> dict:  # type: ignore[type-arg]
    """Build a config dict as configure_providers would load from llm.yaml."""
    return {
        "cheap": {"provider": cheap, "model": f"{cheap}-cheap-model"},
        "expensive": {"provider": expensive, "model": f"{expensive}-expensive-model"},
        "judge": {"provider": judge, "model": f"{judge}-judge-model"},
    }


def _patch_config(cfg: dict) -> patch:  # type: ignore[type-arg]
    """Patch _load_llm_config to return cfg without touching disk."""
    return patch("app.bootstrap._load_llm_config", return_value=cfg)


# ── existing: mock-only yaml (default config) ─────────────────────────────────

class TestBootstrapNoApiKey:
    """All tiers mock → MockProvider in all three slots."""

    def test_bootstrap_no_api_key_wires_mocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _mock_yaml("mock", "mock", "mock")
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        assert isinstance(app.state.reflection_provider, MockProvider)
        assert isinstance(app.state.judge_provider, MockProvider)
        assert isinstance(app.state.narrative_provider, MockProvider)

    def test_bootstrap_no_api_key_providers_are_independent_instances(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _mock_yaml("mock", "mock", "mock")
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        assert app.state.reflection_provider is not app.state.judge_provider
        assert app.state.judge_provider is not app.state.narrative_provider


class TestBootstrapWithApiKey:
    """anthropic provider in yaml + ANTHROPIC_API_KEY set → AnthropicProvider."""

    def test_bootstrap_with_api_key_wires_anthropic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        cfg = _mock_yaml("anthropic", "anthropic", "anthropic")
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        from app.llm.providers.anthropic import AnthropicProvider

        assert isinstance(app.state.reflection_provider, AnthropicProvider)
        assert isinstance(app.state.judge_provider, AnthropicProvider)
        assert isinstance(app.state.narrative_provider, AnthropicProvider)

    def test_bootstrap_with_api_key_model_tiers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        # Explicit model names in config
        cfg = {
            "cheap": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "expensive": {"provider": "anthropic", "model": "claude-opus-4-7"},
            "judge": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        }
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        assert app.state.reflection_provider.model == "claude-haiku-4-5-20251001"
        assert app.state.judge_provider.model == "claude-haiku-4-5-20251001"
        assert app.state.narrative_provider.model == "claude-opus-4-7"


class TestBootstrapIdempotent:
    """Two configure_providers calls replace state cleanly."""

    def test_bootstrap_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _mock_yaml("mock", "mock", "mock")
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)
        first_reflection = app.state.reflection_provider

        with _patch_config(cfg):
            configure_providers(app)
        assert isinstance(app.state.reflection_provider, MockProvider)
        assert app.state.reflection_provider is not first_reflection


class TestCreateAppInvokesBootstrap:
    """create_app() calls bootstrap; providers are non-None."""

    def test_create_app_invokes_bootstrap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("OLDMAN_DB_PATH", str(tmp_path / "test.duckdb"))

        from app.main import create_app

        app = create_app()

        assert getattr(app.state, "reflection_provider", None) is not None
        assert getattr(app.state, "judge_provider", None) is not None
        assert getattr(app.state, "narrative_provider", None) is not None
        assert isinstance(app.state.reflection_provider, MockProvider)


# ── Phase 6.1 new tests ───────────────────────────────────────────────────────

class TestBootstrapOpenRouter:
    """openrouter provider in yaml + OPENROUTER_API_KEY set → OpenRouterProvider."""

    def test_bootstrap_openrouter_when_key_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
        cfg = {
            "cheap": {"provider": "openrouter", "model": "anthropic/claude-haiku-4-5"},
            "expensive": {"provider": "openrouter", "model": "anthropic/claude-opus-4-7"},
            "judge": {"provider": "openrouter", "model": "anthropic/claude-haiku-4-5"},
        }
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        from app.llm.providers.openrouter import OpenRouterProvider

        assert isinstance(app.state.reflection_provider, OpenRouterProvider)
        assert isinstance(app.state.judge_provider, OpenRouterProvider)
        assert isinstance(app.state.narrative_provider, OpenRouterProvider)

    def test_bootstrap_anthropic_when_key_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        cfg = {
            "cheap": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "expensive": {"provider": "anthropic", "model": "claude-opus-4-7"},
            "judge": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        }
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        from app.llm.providers.anthropic import AnthropicProvider

        assert isinstance(app.state.reflection_provider, AnthropicProvider)
        assert isinstance(app.state.narrative_provider, AnthropicProvider)
        assert isinstance(app.state.judge_provider, AnthropicProvider)


class TestBootstrapMixedTiers:
    """Different providers per tier."""

    def test_bootstrap_mixed_tiers_anthropic_judge_openrouter_narrative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
        cfg = {
            "cheap": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "expensive": {"provider": "openrouter", "model": "anthropic/claude-opus-4-7"},
            "judge": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        }
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        from app.llm.providers.anthropic import AnthropicProvider
        from app.llm.providers.openrouter import OpenRouterProvider

        assert isinstance(app.state.reflection_provider, AnthropicProvider)
        assert isinstance(app.state.judge_provider, AnthropicProvider)
        assert isinstance(app.state.narrative_provider, OpenRouterProvider)


class TestBootstrapFallback:
    """Key absent → warn + fall back to MockProvider."""

    def test_bootstrap_warns_and_mocks_when_anthropic_key_absent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = _mock_yaml("anthropic", "anthropic", "anthropic")
        app = FastAPI()
        import logging
        with caplog.at_level(logging.WARNING), _patch_config(cfg):
            configure_providers(app)

        assert isinstance(app.state.reflection_provider, MockProvider)
        assert isinstance(app.state.judge_provider, MockProvider)
        assert isinstance(app.state.narrative_provider, MockProvider)
        # At least one warning about missing key
        assert any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)

    def test_bootstrap_warns_and_mocks_when_openrouter_key_absent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _mock_yaml("openrouter", "openrouter", "openrouter")
        app = FastAPI()
        import logging
        with caplog.at_level(logging.WARNING), _patch_config(cfg):
            configure_providers(app)

        assert isinstance(app.state.reflection_provider, MockProvider)
        assert any("OPENROUTER_API_KEY" in r.message for r in caplog.records)


class TestBootstrapUnknownProvider:
    """Unknown provider name in yaml → ValueError."""

    def test_bootstrap_unknown_provider_raises(self) -> None:
        cfg = _mock_yaml("xprovider", "xprovider", "xprovider")
        app = FastAPI()
        with pytest.raises(ValueError, match="xprovider"), _patch_config(cfg):
            configure_providers(app)


# ── Phase 7.1: bootstrap wires mock modes per tier ───────────────────────────

class TestBootstrapMockModes:
    """Phase 7.1: mock provider in yaml → MockProvider with correct mode per tier."""

    def test_bootstrap_default_config_wires_mock_modes_per_tier(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cheap→reflection, expensive→narrative, judge→judge modes."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _mock_yaml("mock", "mock", "mock")
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        assert isinstance(app.state.reflection_provider, MockProvider)
        assert isinstance(app.state.judge_provider, MockProvider)
        assert isinstance(app.state.narrative_provider, MockProvider)

        assert app.state.reflection_provider.mode == "reflection"
        assert app.state.narrative_provider.mode == "narrative"
        assert app.state.judge_provider.mode == "judge"

    def test_bootstrap_mock_mode_does_not_apply_to_anthropic_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When anthropic key is set, AnthropicProvider is used (no mode attr)."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        cfg = _mock_yaml("anthropic", "anthropic", "anthropic")
        app = FastAPI()
        with _patch_config(cfg):
            configure_providers(app)

        from app.llm.providers.anthropic import AnthropicProvider

        assert isinstance(app.state.reflection_provider, AnthropicProvider)
        assert isinstance(app.state.narrative_provider, AnthropicProvider)
        assert isinstance(app.state.judge_provider, AnthropicProvider)
        # AnthropicProvider has no mode attr
        assert not hasattr(app.state.reflection_provider, "mode")
