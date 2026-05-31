"""Phase 7.0 — Smart MockProvider with context-aware canned responses.

TDD RED tests (7): written before implementation.
"""

from __future__ import annotations

import asyncio

import pytest

from app.llm.base import LLMRequest, LLMTier


def _req(prompt: str = "질문") -> LLMRequest:
    return LLMRequest(system="sys", prompt=prompt, tier=LLMTier.CHEAP, max_tokens=256)


class TestMockBareMode:
    def test_mock_bare_mode_default_returns_mock_string(self) -> None:
        """Default (no mode kwarg) preserves M1 contract: text == '[mock]'."""
        from app.llm.providers.mock import MockProvider

        provider = MockProvider()
        resp = asyncio.run(provider.complete(_req()))
        assert resp.text == "[mock]"

    def test_mock_bare_mode_explicit_returns_mock_string(self) -> None:
        """Explicit mode='bare' also returns '[mock]'."""
        from app.llm.providers.mock import MockProvider

        provider = MockProvider(mode="bare")
        resp = asyncio.run(provider.complete(_req()))
        assert resp.text == "[mock]"


class TestMockReflectionMode:
    def test_mock_reflection_mode_returns_parseable_traits_json(self) -> None:
        """mode='reflection' → valid TraitsCompiled JSON."""
        from app.llm.providers.mock import MockProvider
        from app.reflection.output_schema import TraitsCompiled

        provider = MockProvider(mode="reflection")
        resp = asyncio.run(provider.complete(_req()))
        # Must not raise
        parsed = TraitsCompiled.model_validate_json(resp.text)
        assert isinstance(parsed.summary, str)
        assert isinstance(parsed.descriptors, list)
        assert isinstance(parsed.evidence_event_ids, list)


class TestMockNarrativeMode:
    def test_mock_narrative_mode_extracts_and_cites_evidence_short_ids(self) -> None:
        """mode='narrative' + markers in prompt → response contains those markers."""
        from app.llm.providers.mock import MockProvider

        prompt = "이벤트 목록:\n[↑eaa11bb22] 관찰 · alice\n[↑ecc33dd44] 관찰 · bob\n답변하세요."
        provider = MockProvider(mode="narrative")
        resp = asyncio.run(provider.complete(_req(prompt)))
        assert "[↑eaa11bb22]" in resp.text
        assert "[↑ecc33dd44]" in resp.text

    def test_mock_narrative_mode_no_markers_in_prompt_returns_no_markers(self) -> None:
        """mode='narrative' + no markers in prompt → response without any [↑e...] markers."""
        from app.llm.providers.mock import MockProvider

        provider = MockProvider(mode="narrative")
        resp = asyncio.run(provider.complete(_req("증거 없음.")))
        assert "[↑e" not in resp.text

    def test_mock_narrative_mode_caps_at_three_citations(self) -> None:
        """mode='narrative' caps citations at 3 even when prompt has 10 markers."""
        from app.llm.providers.mock import MockProvider

        markers = " ".join(f"[↑e{i:08x}]" for i in range(10))
        prompt = f"이벤트:\n{markers}\n답변하세요."
        provider = MockProvider(mode="narrative")
        resp = asyncio.run(provider.complete(_req(prompt)))
        # Count occurrences of [↑e in response
        count = resp.text.count("[↑e")
        assert count <= 3, f"expected ≤3 citations in response, got {count}"


class TestMockJudgeMode:
    def test_mock_judge_mode_returns_parseable_verdict_json(self) -> None:
        """mode='judge' → valid JudgeVerdict JSON: is_grounded=True."""
        from app.llm.providers.mock import MockProvider
        from app.narrative.judge import parse_judge_output

        provider = MockProvider(mode="judge")
        resp = asyncio.run(provider.complete(_req()))
        verdict = parse_judge_output(resp.text)
        assert verdict.is_grounded is True
        assert isinstance(verdict.reason, str)


class TestMockUnknownMode:
    def test_mock_unknown_mode_raises_value_error(self) -> None:
        """MockProvider(mode='bogus') → ValueError at construction or complete()."""
        from app.llm.providers.mock import MockProvider

        with pytest.raises(ValueError):
            provider = MockProvider(mode="bogus")
            # If lazy validation, trigger via complete()
            asyncio.run(provider.complete(_req()))
