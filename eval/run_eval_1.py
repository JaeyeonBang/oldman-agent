"""EVAL-1: Reflection accuracy harness.

5개 골든 케이스에 대해 reflection을 생성하고 descriptor jaccard 점수를 측정.

Usage:
    python eval/run_eval_1.py --mock     # 캐닝된 응답 사용 (오프라인, 비용 0)
    python eval/run_eval_1.py --live     # 실제 Anthropic Haiku 호출 (비용 발생)

Score: 평균 jaccard(generated_descriptors, expected_descriptors) ∈ [0, 1].
Pass threshold (M2 baseline): mean ≥ 0.6.

⚠️ 이 파일은 pytest 수집 대상이 아님 (pyproject.toml norecursedirs).
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

# repo root를 path에 추가 (script로 실행될 때)
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# .env 자동 로드 — --live 모드에서 ANTHROPIC_API_KEY를 .env에서 읽도록.
# override=False로 shell export가 우선.
load_dotenv(_REPO_ROOT / ".env", override=False)

from app.llm.base import LLMRequest, LLMResponse, LLMTier  # noqa: E402
from app.reflection.output_schema import TraitsCompiled  # noqa: E402
from app.reflection.prompts import build_user_message, load_prompt  # noqa: E402

_GOLDEN_PATH = _REPO_ROOT / "eval" / "golden_sets" / "reflection_baseline.json"
_PASS_THRESHOLD = 0.6


def jaccard(a: list[str], b: list[str]) -> float:
    """두 descriptor 리스트의 jaccard 유사도."""
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


class _MockGoldenProvider:
    """골든 케이스의 mock_response 필드를 반환하는 provider."""

    name = "mock_golden"
    model = "mock-1"

    def __init__(self, case_responses: dict[str, dict[str, Any]]) -> None:
        self._responses = case_responses
        self._current_case_id: str | None = None

    def set_case(self, case_id: str) -> None:
        self._current_case_id = case_id

    async def complete(self, req: LLMRequest) -> LLMResponse:
        assert self._current_case_id is not None, "set_case() 호출 누락"
        resp = self._responses[self._current_case_id]
        return LLMResponse(
            text=json.dumps(resp, ensure_ascii=False),
            model=self.model,
            tier=req.tier,
            input_tokens=100,
            output_tokens=30,
        )


class _LiveAnthropicProvider:
    """실제 LLM 호출 래퍼 (--live 모드).

    ANTHROPIC_API_KEY가 있으면 Anthropic Haiku, 없고 OPENROUTER_API_KEY가
    있으면 OpenRouter 경유 (OPENROUTER_DEFAULT_MODEL 사용).
    """

    def __init__(self) -> None:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        if anthropic_key:
            from app.llm.providers.anthropic import AnthropicProvider

            self._provider: Any = AnthropicProvider(api_key=anthropic_key)
            self._backend = "anthropic"
        elif openrouter_key:
            from app.llm.providers.openrouter import OpenRouterProvider

            model = os.environ.get(
                "OPENROUTER_DEFAULT_MODEL", "anthropic/claude-haiku-4-5"
            )
            self._provider = OpenRouterProvider(api_key=openrouter_key, model=model)
            self._backend = f"openrouter({model})"
        else:
            raise RuntimeError(
                "ANTHROPIC_API_KEY 또는 OPENROUTER_API_KEY 환경변수가 필요합니다 (--live 모드)"
            )

    async def complete(self, req: LLMRequest) -> LLMResponse:
        return await self._provider.complete(req)


async def _run_case(
    case: dict[str, Any], provider: Any
) -> tuple[float, list[str], list[str]]:
    """단일 케이스 실행 → (jaccard_score, expected, generated_descriptors)."""
    scope = case["scope"]
    system, _ = load_prompt(scope)
    user_msg = build_user_message(case["events"], n=10)

    if isinstance(provider, _MockGoldenProvider):
        provider.set_case(case["id"])

    response = await provider.complete(
        LLMRequest(system=system, prompt=user_msg, tier=LLMTier.CHEAP, max_tokens=1024)
    )
    try:
        parsed = TraitsCompiled.model_validate_json(response.text)
    except Exception as exc:
        print(f"  [ERROR] {case['id']}: 응답 파싱 실패: {exc}", file=sys.stderr)
        return 0.0, case["expected_descriptors"], []

    score = jaccard(parsed.descriptors, case["expected_descriptors"])
    return score, case["expected_descriptors"], parsed.descriptors


async def main() -> int:
    parser = argparse.ArgumentParser(description="EVAL-1 reflection accuracy harness")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="캐닝된 응답 사용 (비용 0)")
    mode.add_argument("--live", action="store_true", help="실제 Anthropic 호출 (비용)")
    args = parser.parse_args()

    with _GOLDEN_PATH.open(encoding="utf-8") as f:
        golden = json.load(f)
    cases = golden["cases"]

    if args.mock:
        provider: Any = _MockGoldenProvider(
            {c["id"]: c["mock_response"] for c in cases}
        )
        mode_label = "MOCK"
    else:
        provider = _LiveAnthropicProvider()
        mode_label = "LIVE"

    print(f"EVAL-1 reflection accuracy ({mode_label} mode)")
    print(f"  golden set: {_GOLDEN_PATH.name} — {len(cases)} cases")
    print("=" * 60)

    scores: list[float] = []
    for case in cases:
        score, expected, generated = await _run_case(case, provider)
        scores.append(score)
        status = "PASS" if score >= _PASS_THRESHOLD else "WARN"
        print(f"[{status}] {case['id']}: jaccard={score:.3f}")
        print(f"  expected:  {expected}")
        print(f"  generated: {generated}")

    mean_score = sum(scores) / len(scores) if scores else 0.0
    print("=" * 60)
    print(f"Mean jaccard: {mean_score:.3f} (threshold ≥ {_PASS_THRESHOLD})")

    overall_pass = mean_score >= _PASS_THRESHOLD
    print(f"Overall: {'PASS' if overall_pass else 'FAIL'}")
    return 0  # 항상 0 반환 (acceptance: prints score, exits 0)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
