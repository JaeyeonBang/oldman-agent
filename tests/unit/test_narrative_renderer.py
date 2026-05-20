"""Phase 3.4 — RED tests: narrative renderer + retry loop."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from app.llm.base import LLMRequest, LLMResponse


def _insert_event(conn, *, source_agent: str = "agent_alice", kind: str = "observation") -> str:
    event_id = str(uuid.uuid4())
    ts = datetime.now(UTC)
    conn.execute(
        "INSERT INTO events (event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (?, ?, ?, ?, 'self', ?, ?)",
        [event_id, ts, kind, source_agent, json.dumps({"msg": "test"}), uuid.uuid4().hex],
    )
    return event_id


def _insert_reflection(conn, *, scope: str = "agent", subject: str = "agent_alice") -> None:
    rid = str(uuid.uuid4())
    ts = datetime.now(UTC)
    conn.execute(
        "INSERT INTO reflections "
        "(reflection_id, ts, scope, subject, text, event_range_start, event_range_end, source_event_ids) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [rid, ts, scope, subject, "test reflection", ts, ts, "[]"],
    )


class _ValidProvider:
    """항상 valid 인용 마커가 있는 텍스트를 반환하는 Provider."""
    name = "valid"
    model = "valid-1"

    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        self.calls = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        short_id = self.event_id[:8]
        text = f"agent_alice가 행동을 했습니다 [↑e{short_id}]."
        return LLMResponse(text=text, model=self.model, tier=req.tier)


class _InvalidThenValidProvider:
    """첫 호출은 invalid(bogus 마커), 두 번째는 valid 반환."""
    name = "invalid_then_valid"
    model = "itv-1"

    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        self.calls = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            # 존재하지 않는 short_id 사용 → validator 실패
            text = "agent_alice가 행동했습니다 [↑eff000000]."
        else:
            short_id = self.event_id[:8]
            text = f"agent_alice가 행동을 했습니다 [↑e{short_id}]."
        return LLMResponse(text=text, model=self.model, tier=req.tier)


class _AlwaysInvalidProvider:
    """항상 invalid 인용 마커를 반환."""
    name = "always_invalid"
    model = "ai-1"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="agent_alice가 무언가를 했습니다 [↑eff000000].",
            model=self.model,
            tier=req.tier,
        )


class _RaisingProvider:
    """complete 호출 시 예외 발생."""
    name = "raising"
    model = "raise-1"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        raise RuntimeError("LLM 폭발")


class TestRenderNarrative:
    @pytest.mark.asyncio
    async def test_render_cold_start_returns_fallback_no_provider_call(
        self, tmp_db
    ) -> None:
        from app.narrative.renderer import render_narrative
        from app.state.cold_start import COLD_START_FALLBACK_MESSAGE

        provider = _RaisingProvider()
        result = await render_narrative(tmp_db, provider, "질문", None)
        assert result.is_cold_start is True
        assert result.answer == COLD_START_FALLBACK_MESSAGE
        assert result.used_fallback is True
        # provider가 호출되지 않아야 함 (RaisingProvider지만 예외 없어야 함)

    @pytest.mark.asyncio
    async def test_render_empty_evidence_returns_fallback_no_provider_call(
        self, tmp_db
    ) -> None:
        from app.narrative.renderer import render_narrative
        from app.state.cold_start import COLD_START_FALLBACK_MESSAGE

        # cold_start 통과용: event + reflection 최소 1개씩 삽입
        _insert_event(tmp_db)
        _insert_reflection(tmp_db)
        # cold start 아님이지만, subject_agent 필터로 evidence 없게 만듦
        provider = _RaisingProvider()
        result = await render_narrative(tmp_db, provider, "질문", "agent_nobody")
        assert result.used_fallback is True
        assert result.answer == COLD_START_FALLBACK_MESSAGE

    @pytest.mark.asyncio
    async def test_render_first_attempt_valid_returns_immediately(
        self, tmp_db
    ) -> None:
        from app.narrative.renderer import render_narrative

        eid = _insert_event(tmp_db)
        _insert_reflection(tmp_db)
        provider = _ValidProvider(eid)
        result = await render_narrative(tmp_db, provider, "질문", "agent_alice")
        assert result.used_fallback is False
        assert result.retries_used == 0
        assert len(result.citations) >= 1
        assert provider.calls == 1

    @pytest.mark.asyncio
    async def test_render_invalid_first_then_valid_returns_with_retries_used_1(
        self, tmp_db
    ) -> None:
        from app.narrative.renderer import render_narrative

        eid = _insert_event(tmp_db)
        _insert_reflection(tmp_db)
        provider = _InvalidThenValidProvider(eid)
        result = await render_narrative(tmp_db, provider, "질문", "agent_alice", max_retries=2)
        assert result.used_fallback is False
        assert result.retries_used == 1
        assert provider.calls == 2

    @pytest.mark.asyncio
    async def test_render_all_attempts_invalid_returns_fallback(
        self, tmp_db
    ) -> None:
        from app.narrative.renderer import render_narrative
        from app.state.cold_start import COLD_START_FALLBACK_MESSAGE

        _insert_event(tmp_db)
        _insert_reflection(tmp_db)
        provider = _AlwaysInvalidProvider()
        result = await render_narrative(tmp_db, provider, "질문", "agent_alice", max_retries=2)
        assert result.used_fallback is True
        assert result.answer == COLD_START_FALLBACK_MESSAGE
        assert result.retries_used == 2

    @pytest.mark.asyncio
    async def test_render_provider_raises_returns_fallback(
        self, tmp_db
    ) -> None:
        from app.narrative.renderer import render_narrative
        from app.state.cold_start import COLD_START_FALLBACK_MESSAGE

        _insert_event(tmp_db)
        _insert_reflection(tmp_db)
        provider = _RaisingProvider()
        # provider가 예외를 던져도 HTTP 500 없이 fallback 반환해야 함
        result = await render_narrative(tmp_db, provider, "질문", "agent_alice")
        assert result.used_fallback is True
        assert result.answer == COLD_START_FALLBACK_MESSAGE


# ── Phase 4.3 — strict mode tests ────────────────────────────────────────────

class _GroundedJudgeProvider:
    """항상 is_grounded=True 반환하는 judge provider."""
    name = "grounded_judge"
    model = "gj-1"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text='{"is_grounded": true, "reason": "일치"}',
            model=self.model,
            tier=req.tier,
        )


class _UngroundedJudgeProvider:
    """항상 is_grounded=False 반환하는 judge provider."""
    name = "ungrounded_judge"
    model = "uj-1"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text='{"is_grounded": false, "reason": "날조"}',
            model=self.model,
            tier=req.tier,
        )


class TestRenderNarrativeStrictMode:
    @pytest.mark.asyncio
    async def test_renderer_strict_mode_calls_judge_when_existence_passes(
        self, tmp_db
    ) -> None:
        """strict 모드에서 존재 검증 통과 후 judge가 호출되어야 한다."""
        from app.narrative.renderer import render_narrative

        eid = _insert_event(tmp_db)
        _insert_reflection(tmp_db)
        narrative_provider = _ValidProvider(eid)
        judge_provider = _GroundedJudgeProvider()

        result = await render_narrative(
            tmp_db,
            narrative_provider,
            "질문",
            "agent_alice",
            validator_mode="strict",
            judge_provider=judge_provider,
        )

        assert result.used_fallback is False
        assert judge_provider.calls >= 1

    @pytest.mark.asyncio
    async def test_renderer_strict_ungrounded_triggers_retry_with_ungrounded_hint(
        self, tmp_db
    ) -> None:
        """strict 모드에서 ungrounded 판정 → 재시도 + 힌트 메시지 다름."""
        from app.narrative.renderer import render_narrative

        eid = _insert_event(tmp_db)
        _insert_reflection(tmp_db)
        # narrative provider는 항상 valid 인용을 반환 (존재 검증 통과)
        narrative_provider = _ValidProvider(eid)
        # judge는 항상 ungrounded → 재시도 강제
        judge_provider = _UngroundedJudgeProvider()

        result = await render_narrative(
            tmp_db,
            narrative_provider,
            "질문",
            "agent_alice",
            max_retries=1,
            validator_mode="strict",
            judge_provider=judge_provider,
        )

        # 모든 시도가 ungrounded → fallback
        assert result.used_fallback is True
        assert result.retries_used == 1

    @pytest.mark.asyncio
    async def test_renderer_strict_mode_default_judge_provider_none_raises_helpful_error(
        self, tmp_db
    ) -> None:
        """strict 모드에서 judge_provider=None이면 ValueError를 즉시 발생시킨다."""
        from app.narrative.renderer import render_narrative

        _insert_event(tmp_db)
        _insert_reflection(tmp_db)
        provider = _ValidProvider("aa11bb22-0000-0000-0000-000000000000")

        with pytest.raises(ValueError, match="judge_provider"):
            await render_narrative(
                tmp_db,
                provider,
                "질문",
                "agent_alice",
                validator_mode="strict",
                judge_provider=None,
            )
