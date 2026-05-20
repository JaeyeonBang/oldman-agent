"""Phase 4.2 — RED tests: validate_citations_with_judge (strict validator)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.llm.base import LLMRequest, LLMResponse
from app.narrative.evidence import EventRow, Evidence

# ── CannedJudge test doubles ──────────────────────────────────────────────────

class _AlwaysGroundedJudge:
    """모든 판정에서 is_grounded=True를 반환."""
    name = "always_grounded"
    model = "grounded-1"

    def __init__(self) -> None:
        self.calls: int = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text='{"is_grounded": true, "reason": "일치"}',
            model=self.model,
            tier=req.tier,
        )


class _AlwaysUngroundedJudge:
    """모든 판정에서 is_grounded=False를 반환."""
    name = "always_ungrounded"
    model = "ungrounded-1"

    def __init__(self) -> None:
        self.calls: int = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text='{"is_grounded": false, "reason": "페이로드 불일치"}',
            model=self.model,
            tier=req.tier,
        )


class _PerCitationJudge:
    """short_id별로 다른 판정을 반환하는 Judge."""
    name = "per_citation"
    model = "per-1"

    def __init__(self, grounded_ids: set[str]) -> None:
        self._grounded = grounded_ids
        self.calls: int = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        # prompt에 grounded_ids의 short_id가 포함되어 있으면 grounded
        is_grounded = any(sid in req.prompt for sid in self._grounded)
        verdict = "true" if is_grounded else "false"
        return LLMResponse(
            text=f'{{"is_grounded": {verdict}, "reason": "test"}}',
            model=self.model,
            tier=req.tier,
        )


class _RaisingJudge:
    """complete 호출 시 항상 예외 발생."""
    name = "raising_judge"
    model = "raise-1"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        raise RuntimeError("judge 폭발")


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_event(event_id: str, payload: dict | None = None) -> EventRow:
    return EventRow(
        event_id=event_id,
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        kind="observation",
        source_agent="agent_alice",
        source_type="self",
        payload=payload or {"msg": "test"},
    )


def _make_evidence(*event_ids: str) -> Evidence:
    return Evidence(
        events=[_make_event(eid) for eid in event_ids],
        reflections=[],
    )


# ── tests ─────────────────────────────────────────────────────────────────────

class TestValidateCitationsWithJudge:
    @pytest.mark.asyncio
    async def test_strict_validator_all_grounded_passes(self) -> None:
        from app.narrative.validator import validate_citations_with_judge

        eid = "aa11bb22-0000-0000-0000-000000000000"
        evidence = _make_evidence(eid)
        text = f"agent_alice가 행동했습니다 [↑e{eid[:8]}]."

        judge = _AlwaysGroundedJudge()
        result = await validate_citations_with_judge(text, evidence, judge)

        assert result.is_valid is True
        assert result.missing == []
        assert result.ungrounded == []
        assert judge.calls == 1

    @pytest.mark.asyncio
    async def test_strict_validator_one_ungrounded_fails_with_citation_listed(
        self,
    ) -> None:
        from app.narrative.validator import validate_citations_with_judge

        eid = "cc33dd44-0000-0000-0000-000000000000"
        evidence = _make_evidence(eid)
        text = f"agent_alice가 행동했습니다 [↑e{eid[:8]}]."

        judge = _AlwaysUngroundedJudge()
        result = await validate_citations_with_judge(text, evidence, judge)

        assert result.is_valid is False
        assert result.missing == []
        assert len(result.ungrounded) == 1
        assert result.ungrounded[0].short_id == eid[:8]

    @pytest.mark.asyncio
    async def test_strict_validator_existence_failure_short_circuits_no_judge_call(
        self,
    ) -> None:
        """존재 검증 실패 시 judge 호출 없이 조기 반환."""
        from app.narrative.validator import validate_citations_with_judge

        # evidence에 없는 short_id 사용 → 존재 검증 실패
        eid_in_evidence = "aa11bb22-0000-0000-0000-000000000000"
        evidence = _make_evidence(eid_in_evidence)
        text = "agent_alice가 행동했습니다 [↑eff000000]."  # 없는 short_id

        judge = _AlwaysGroundedJudge()
        result = await validate_citations_with_judge(text, evidence, judge)

        assert result.is_valid is False
        assert "ff000000" in result.missing
        # judge 호출이 없어야 함
        assert judge.calls == 0

    @pytest.mark.asyncio
    async def test_strict_validator_judge_provider_exception_falls_back_to_existence_only(
        self,
    ) -> None:
        """judge provider 예외 → is_grounded=False(provider_error) → ungrounded 처리.

        Plan §3 Phase 4.2: provider exception → judge result treated as "assume grounded"
        → existence-only outcome holds.
        """
        from app.narrative.validator import validate_citations_with_judge

        eid = "ee55ff66-0000-0000-0000-000000000000"
        evidence = _make_evidence(eid)
        text = f"agent_alice가 행동했습니다 [↑e{eid[:8]}]."

        judge = _RaisingJudge()
        result = await validate_citations_with_judge(text, evidence, judge)

        # judge 예외 → graceful degradation → existence-only (valid=True)
        assert result.is_valid is True
        assert result.ungrounded == []

    @pytest.mark.asyncio
    async def test_strict_validator_each_citation_judged_independently(self) -> None:
        """두 개 인용 중 하나만 ungrounded → 그것만 ungrounded 목록에."""
        from app.narrative.validator import validate_citations_with_judge

        eid1 = "11112222-0000-0000-0000-000000000000"
        eid2 = "33334444-0000-0000-0000-000000000000"
        evidence = _make_evidence(eid1, eid2)

        # eid1은 grounded, eid2는 ungrounded로 판정
        judge = _PerCitationJudge(grounded_ids={eid1[:8]})
        text = (
            f"첫 인용 [↑e{eid1[:8]}]입니다. "
            f"두 번째 인용 [↑e{eid2[:8]}]입니다."
        )
        result = await validate_citations_with_judge(text, evidence, judge)

        assert result.is_valid is False
        assert len(result.ungrounded) == 1
        assert result.ungrounded[0].short_id == eid2[:8]
        assert judge.calls == 2
