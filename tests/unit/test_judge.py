"""Phase 4.0 — RED tests: LLM judge grounding verdict + parser."""

from __future__ import annotations

import pytest

from app.llm.base import LLMRequest, LLMResponse

# ── CannedJudge test double ───────────────────────────────────────────────────

class _CannedJudgeProvider:
    """판정 텍스트를 캐닝해 반환하는 테스트용 Provider."""

    name = "canned_judge"
    model = "judge-mock-1"

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.calls: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls.append(req)
        return LLMResponse(
            text=self._response_text,
            model=self.model,
            tier=req.tier,
        )


class _RaisingJudgeProvider:
    """complete 호출 시 예외를 발생시키는 테스트용 Provider."""

    name = "raising_judge"
    model = "raise-mock-1"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        raise RuntimeError("judge provider 폭발")


# ── parse_judge_output 단위 테스트 ────────────────────────────────────────────

class TestParseJudgeOutput:
    def test_parse_judge_output_valid_json_grounded(self) -> None:
        from app.narrative.judge import parse_judge_output

        text = '{"is_grounded": true, "reason": "payload 내용과 일치합니다"}'
        verdict = parse_judge_output(text)
        assert verdict.is_grounded is True
        assert "일치" in verdict.reason

    def test_parse_judge_output_valid_json_hallucinated(self) -> None:
        from app.narrative.judge import parse_judge_output

        text = '{"is_grounded": false, "reason": "agent_name이 payload에 없습니다"}'
        verdict = parse_judge_output(text)
        assert verdict.is_grounded is False
        assert verdict.reason != ""

    def test_parse_judge_output_malformed_returns_false_with_parse_error_reason(
        self,
    ) -> None:
        from app.narrative.judge import parse_judge_output

        verdict = parse_judge_output("이것은 JSON이 아닙니다. 완전히 쓰레기 텍스트.")
        assert verdict.is_grounded is False
        assert verdict.reason == "parse_error"

    def test_parse_judge_output_leading_prose_extracted(self) -> None:
        """JSON 앞뒤에 프로즈가 있어도 파싱되어야 한다."""
        from app.narrative.judge import parse_judge_output

        text = (
            "네, 분석 결과입니다:\n"
            '{"is_grounded": true, "reason": "근거 있음"}\n'
            "이상입니다."
        )
        verdict = parse_judge_output(text)
        assert verdict.is_grounded is True


# ── judge_grounding 통합 단위 테스트 ─────────────────────────────────────────

class TestJudgeGrounding:
    @pytest.mark.asyncio
    async def test_judge_grounding_calls_provider_with_correct_prompt_shape(
        self,
    ) -> None:
        """Provider가 system + user 메시지를 올바른 형태로 받는지 확인."""
        from app.narrative.judge import judge_grounding

        response_json = '{"is_grounded": true, "reason": "일치"}'
        provider = _CannedJudgeProvider(response_json)

        claim = "agent_alice가 2026년 1월에 등록했습니다."
        payload = {"action": "register", "agent": "agent_alice", "month": "2026-01"}

        verdict = await judge_grounding(provider, claim, payload)

        assert verdict.is_grounded is True
        assert len(provider.calls) == 1
        req = provider.calls[0]
        # system 프롬프트에 Korean 가이드가 포함되어야 함
        assert len(req.system) > 100
        # user prompt에 claim과 payload가 포함되어야 함
        assert "agent_alice" in req.prompt or "register" in req.prompt

    @pytest.mark.asyncio
    async def test_judge_grounding_provider_exception_returns_false_with_provider_error_reason(
        self,
    ) -> None:
        """Provider 예외 → is_grounded=False, reason='provider_error'."""
        from app.narrative.judge import judge_grounding

        provider = _RaisingJudgeProvider()
        verdict = await judge_grounding(provider, "어떤 주장", {"key": "val"})

        assert verdict.is_grounded is False
        assert verdict.reason == "provider_error"
