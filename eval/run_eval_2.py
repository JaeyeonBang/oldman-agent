#!/usr/bin/env python3
"""EVAL-2: Citation Grounding — 100-case content-grounded validator harness.

Mock mode: RuleBasedMockJudge — FABRICATED_ 키워드 포함 시 is_grounded=False 반환.
           결정론적, 비용 0. CI에서 사용.
Live mode: 실제 Anthropic Haiku judge 호출 (비용 발생, 약 $0.04/run).

Usage:
    python eval/run_eval_2.py --mock     # CI (비용 0)
    python eval/run_eval_2.py --live     # 실제 judge 호출

Output:
    === EVAL-2: Citation Grounding ===
    Total cases: 100  (grounded: 70, hallucinated: 30)
    True positives (correctly flagged hallucinated): NN / 30
    False positives (grounded flagged as hallucinated): NN / 70
    False negatives (hallucinated missed): NN / 30
    Hallucination rate after validator: X.XX%
    Threshold < 1% → PASS / FAIL

Exit code:
    0 — PASS
    1 — FAIL

⚠️ 이 파일은 CLAUDE.md EVAL 트리거 대상. 변경 시 EVAL-2 재실행 필요.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# .env 자동 로드 — --live 모드에서 ANTHROPIC_API_KEY를 .env에서 읽도록.
load_dotenv(_REPO_ROOT / ".env", override=False)

from app.llm.base import LLMRequest, LLMResponse  # noqa: E402
from app.narrative.evidence import EventRow, Evidence  # noqa: E402

_GOLDEN_PATH = _REPO_ROOT / "eval" / "golden_sets" / "citation_grounding.json"
_HALLUCINATION_THRESHOLD = 0.01  # 1%


# ── Mock judge ────────────────────────────────────────────────────────────────

class RuleBasedMockJudge:
    """결정론적 rule-based mock judge.

    FABRICATED_ 키워드가 narrative에 포함되어 있으면 → is_grounded=False.
    그 외 → is_grounded=True.

    이 규칙은 골든 세트 생성기(_seed_golden_set.py)의 마커 규칙과 대응된다.
    """

    name = "rule_based_mock_judge"
    model = "mock-judge-1"

    def __init__(self) -> None:
        self.calls: int = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        # user prompt에 claim이 포함됨; FABRICATED_ 키워드 확인
        is_grounded = "FABRICATED_" not in req.prompt
        verdict = "true" if is_grounded else "false"
        reason = "grounded" if is_grounded else "FABRICATED_ 키워드 감지"
        return LLMResponse(
            text=f'{{"is_grounded": {verdict}, "reason": "{reason}"}}',
            model=self.model,
            tier=req.tier,
        )


# ── Live judge (Anthropic Haiku) ──────────────────────────────────────────────

class _LiveAnthropicJudge:
    """실제 Anthropic Haiku judge (--live 모드)."""

    def __init__(self) -> None:
        from app.llm.providers.anthropic import AnthropicProvider

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 필요합니다 (--live 모드)")
        self._provider = AnthropicProvider(
            model="claude-haiku-4-5-20251001",
            api_key=api_key,
        )

    async def complete(self, req: LLMRequest) -> LLMResponse:
        return await self._provider.complete(req)


# ── Case runner ───────────────────────────────────────────────────────────────

async def _run_case(
    case: dict[str, Any],
    judge_provider: Any,
    *,
    existence_only: bool = False,
) -> tuple[bool, bool]:
    """단일 케이스 실행.

    Returns:
        (existence_passed, strict_passed) — 존재 검증과 strict 검증 각각의 통과 여부.
    """
    from datetime import UTC, datetime

    from app.narrative.validator import validate_citations, validate_citations_with_judge

    # evidence 구성
    events = [
        EventRow(
            event_id=ev["event_id"],
            ts=datetime(2026, 1, 1, tzinfo=UTC),
            kind=ev["kind"],
            source_agent=ev["source_agent"],
            source_type="self",
            payload=ev["payload"],
        )
        for ev in case["evidence_events"]
    ]
    evidence = Evidence(events=events, reflections=[])
    text = case["narrative"]

    # 존재 검증
    existence_result = validate_citations(text, evidence)
    existence_passed = existence_result.is_valid

    if existence_only:
        return existence_passed, existence_passed

    # strict 검증
    strict_result = await validate_citations_with_judge(text, evidence, judge_provider)
    strict_passed = strict_result.is_valid

    return existence_passed, strict_passed


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description="EVAL-2 citation grounding harness")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="결정론적 mock judge 사용 (비용 0)")
    mode.add_argument("--live", action="store_true", help="실제 Anthropic Haiku judge (비용)")
    args = parser.parse_args()

    with _GOLDEN_PATH.open(encoding="utf-8") as f:
        golden = json.load(f)

    cases = golden["cases"]
    total_grounded = golden["grounded"]
    total_hallucinated = golden["hallucinated"]

    if args.mock:
        judge: Any = RuleBasedMockJudge()
        mode_label = "MOCK"
    else:
        judge = _LiveAnthropicJudge()
        mode_label = "LIVE"

    print(f"=== EVAL-2: Citation Grounding ({mode_label} mode) ===")
    print(f"Golden set: {_GOLDEN_PATH.name} — {len(cases)} cases")
    print(f"  grounded: {total_grounded}, hallucinated: {total_hallucinated}")
    print("=" * 60)

    # 결과 집계
    tp = 0  # true positive: hallucinated → correctly flagged
    fp = 0  # false positive: grounded → incorrectly flagged
    fn = 0  # false negative: hallucinated → missed (passed)

    existence_fn = 0  # 존재 검증이 놓친 hallucinated (strict가 잡아야 할 대상)
    strict_caught_delta = 0  # strict가 추가로 잡은 hallucinated (existence 통과한 것)

    category_counts: dict[str, dict[str, int]] = {}

    for case in cases:
        existence_passed, strict_passed = await _run_case(case, judge)

        expected_hallucination: bool = case["expected_hallucination"]
        cat = case["category"]

        if cat not in category_counts:
            category_counts[cat] = {"total": 0, "caught": 0}
        category_counts[cat]["total"] += 1

        if expected_hallucination:
            if not existence_passed:
                # 존재 검증도 잡음 (short_id가 없는 경우)
                pass
            elif not strict_passed:
                # strict가 잡음 (existence 통과했지만 strict는 실패)
                existence_fn += 1
                strict_caught_delta += 1
                category_counts[cat]["caught"] += 1

            if not strict_passed:
                tp += 1
            else:
                fn += 1
        else:
            # grounded case
            if not strict_passed:
                fp += 1

    print(f"Total cases: {len(cases)}  (grounded: {total_grounded}, hallucinated: {total_hallucinated})")
    print(f"True positives  (correctly flagged hallucinated): {tp} / {total_hallucinated}")
    print(f"False positives (grounded flagged as hallucinated): {fp} / {total_grounded}")
    print(f"False negatives (hallucinated missed): {fn} / {total_hallucinated}")
    print()

    # hallucination rate: strict validator 통과한 hallucinated / total citations
    total_citations = sum(len(c["evidence_events"]) for c in cases)
    survived_hallucinations = fn
    hallucination_rate = survived_hallucinations / total_citations if total_citations else 0.0

    print(f"Hallucination rate after validator: {survived_hallucinations} / {total_citations} = {hallucination_rate:.2%}")
    print(f"Threshold < {_HALLUCINATION_THRESHOLD:.0%} → ", end="")

    passed = hallucination_rate < _HALLUCINATION_THRESHOLD
    print("PASS" if passed else "FAIL")

    print()
    print("--- Per-category breakdown ---")
    for cat, counts in sorted(category_counts.items()):
        if cat == "grounded":
            print(f"  {cat}: {counts['total']} cases, {fp} false positives")
        else:
            print(f"  {cat}: {counts['total']} cases, {counts['caught']} caught by strict (not existence)")

    # 데모 블록: existence 통과 → strict 잡음 케이스 1개 출력
    print()
    print("--- Demonstrable block: existence-pass but strict-catches ---")
    demo_shown = False
    for case in cases:
        if not case["expected_hallucination"]:
            continue
        existence_passed, strict_passed = await _run_case(case, judge)
        if existence_passed and not strict_passed:
            print(f"  Case ID: {case['id']} ({case['category']})")
            print(f"  Narrative: {case['narrative']}")
            ev = case["evidence_events"][0]
            print(f"  Evidence payload: {json.dumps(ev['payload'], ensure_ascii=False)}")
            print("  Existence check: PASS (short_id exists in evidence)")
            print("  Strict check:    FAIL (judge: is_grounded=False)")
            demo_shown = True
            break

    if not demo_shown:
        print("  (해당 케이스 없음 — mock judge 또는 골든 세트 구성 확인 필요)")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
