"""Paraphrase 일관성 게이트 — 고액 매입 전 무료급 사전 검사 (P3).

같은 질문을 바꿔 묻거나 복수 신원으로 물어 답들의 합치도를 잰다. 낮은
합치도 = 조작/헛소리 신호 (SelfCheckGPT/semantic entropy의 결정적 근사 —
tokenize + pairwise jaccard, LLM 불요라 mock 모드에서도 동일 동작).

한계 (정직한 프레이밍): 일관된 거짓말은 통과한다 — 이 게이트는 '성의 없는
조작'을 거르는 1차 필터이고, 정직성 판정은 canary(canary.py)의 몫.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from app.storage.dedup import tokenize

DEFAULT_CONSISTENCY_THRESHOLD = 0.6


@dataclass(frozen=True)
class ProbeVerdict:
    passed: bool
    score: float
    n_answers: int


def check_consistency(
    answers: list[dict[str, Any]],
    *,
    threshold: float = DEFAULT_CONSISTENCY_THRESHOLD,
) -> ProbeVerdict:
    """답변들의 평균 pairwise jaccard 합치도. 2개 미만이면 ValueError."""
    if len(answers) < 2:
        raise ValueError("consistency probe needs at least 2 answers")
    token_sets = [tokenize(a) for a in answers]
    scores = []
    for a, b in combinations(token_sets, 2):
        union = a | b
        scores.append(len(a & b) / len(union) if union else 1.0)
    score = sum(scores) / len(scores)
    return ProbeVerdict(passed=score >= threshold, score=score, n_answers=len(answers))
