"""P4 마무리 — 평판 narrative LLM 레이어 (TDD).

핵심 안전 성질: 발명된 citation 마커는 절대 나가지 않는다 (template fallback).
"""

from __future__ import annotations

import pytest

from app.llm.base import LLMRequest, LLMResponse, LLMTier
from app.narrative.reputation import render_reputation_narrative
from app.trust.report import ReportCitation, ReputationReport


class FakeProvider:
    def __init__(self, text: str | None = None, raises: bool = False) -> None:
        self._text = text or ""
        self._raises = raises
        self.last_request: LLMRequest | None = None

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.last_request = req
        if self._raises:
            raise RuntimeError("provider down")
        return LLMResponse(text=self._text, model="fake", tier=LLMTier.CHEAP)


def _report(with_citations: bool = True) -> ReputationReport:
    citations = (
        [
            ReportCitation(
                short_id="abcd1234",
                trust_event_id="abcd1234-full",
                cause="canary_fail",
            )
        ]
        if with_citations
        else []
    )
    return ReputationReport(
        subject_agent="liar_bot",
        state="penalized",
        violation_count=3,
        text="TEMPLATE: 내가 보기엔 liar_bot 그놈은... [↑abcd1234]",
        citations=citations,
    )


@pytest.mark.asyncio
async def test_no_provider_uses_template() -> None:
    text, used_llm = await render_reputation_narrative(None, _report())
    assert used_llm is False
    assert text.startswith("TEMPLATE:")


@pytest.mark.asyncio
async def test_no_citations_skips_llm() -> None:
    provider = FakeProvider(text="이건 쓰이면 안 됨")
    _text, used_llm = await render_reputation_narrative(
        provider, _report(with_citations=False)
    )
    assert used_llm is False
    assert provider.last_request is None  # LLM 호출 자체가 없음


@pytest.mark.asyncio
async def test_valid_persona_output_is_used() -> None:
    provider = FakeProvider(
        text="내가 보기엔 liar_bot 그놈은 영 글렀구먼 [↑abcd1234]. 늙은이 소견일세."
    )
    text, used_llm = await render_reputation_narrative(
        provider, _report(), persona="kkondae"
    )
    assert used_llm is True
    assert "[↑abcd1234]" in text
    assert provider.last_request is not None
    assert "꼰대" in provider.last_request.system  # persona 프롬프트 로드 확인


@pytest.mark.asyncio
async def test_invented_marker_falls_back_to_template() -> None:
    provider = FakeProvider(text="그놈은 도둑이야 [↑ffff9999]. 확실하네.")
    text, used_llm = await render_reputation_narrative(provider, _report())
    assert used_llm is False
    assert text.startswith("TEMPLATE:")


@pytest.mark.asyncio
async def test_output_without_any_marker_falls_back() -> None:
    provider = FakeProvider(text="그놈은 나쁜 놈이야. 근거는 묻지 말게.")
    _text, used_llm = await render_reputation_narrative(provider, _report())
    assert used_llm is False


@pytest.mark.asyncio
async def test_provider_error_falls_back() -> None:
    provider = FakeProvider(raises=True)
    text, used_llm = await render_reputation_narrative(provider, _report())
    assert used_llm is False
    assert text.startswith("TEMPLATE:")
