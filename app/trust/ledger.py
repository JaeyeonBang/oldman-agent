"""Trust Ledger 도메인 — Beta(alpha, beta) 점수, 비대칭 update, 시간 감쇠 (P1).

설계 근거 (research/agent-trust-impl-plan-2026-07.md §3 P1, 1차 리서치 §2.4):
  - Beta/Subjective Logic: 불확실성이 1급 시민 — 신규는 "미지"(낮은 prior +
    높은 분산)이지 "중립"이 아니다 (whitewashing 차단).
  - 비대칭 동역학: 부정 증거를 ``fall_multiplier``배 가중 — 느리게 오르고
    빠르게 떨어진다 (on-off 공격 방어).
  - 지수 감쇠: 증거 질량이 prior로 회귀 — 최근 행동이 지배하고, 오래되면
    불확실성이 회복된다.

DB 접근 없음 — 순수 함수. 저장은 app/storage/trust.py, 오케스트레이션은
app/trust/service.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BetaScore:
    alpha: float
    beta: float

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def std(self) -> float:
        n = self.alpha + self.beta
        return math.sqrt(self.alpha * self.beta / (n * n * (n + 1.0)))

    @property
    def observations(self) -> float:
        """prior 대비 누적 증거 질량 (거래액 가중 포함)."""
        return (self.alpha - COLD_START_PRIOR.alpha) + (
            self.beta - COLD_START_PRIOR.beta
        )

    def lower_bound(self, z: float = 1.0) -> float:
        """보수적 신뢰 추정 — mean - z*std (제재 판단은 이 값 기준)."""
        return max(0.0, self.mean - z * self.std)


#: 신규 = 낮은 prior(mean 0.25) + 높은 불확실성(std ≈ 0.19). "미지" ≠ "중립".
COLD_START_PRIOR = BetaScore(alpha=1.0, beta=3.0)


@dataclass(frozen=True)
class LedgerPolicy:
    """감쇠·비대칭 파라미터. 초기값은 plan §3 — 운영 데이터로 보정 예정."""

    fall_multiplier: float = 4.0
    reliability_half_life_days: float = 30.0
    honesty_half_life_days: float = 60.0

    def half_life_for(self, criterion: str) -> float:
        if criterion == "honesty":
            return self.honesty_half_life_days
        return self.reliability_half_life_days


DEFAULT_POLICY = LedgerPolicy()


def update(
    score: BetaScore,
    *,
    positive: bool,
    weight: float = 1.0,
    policy: LedgerPolicy = DEFAULT_POLICY,
) -> BetaScore:
    """증거 1건 반영. 부정 증거는 fall_multiplier배 — 비대칭 동역학."""
    if positive:
        return BetaScore(alpha=score.alpha + weight, beta=score.beta)
    return BetaScore(
        alpha=score.alpha, beta=score.beta + weight * policy.fall_multiplier
    )


def decay(
    score: BetaScore,
    *,
    elapsed_days: float,
    half_life_days: float,
    prior: BetaScore = COLD_START_PRIOR,
) -> BetaScore:
    """경과 시간만큼 증거 질량을 prior로 지수 회귀."""
    if elapsed_days <= 0.0:
        return score
    factor = 0.5 ** (elapsed_days / half_life_days)
    return BetaScore(
        alpha=prior.alpha + (score.alpha - prior.alpha) * factor,
        beta=prior.beta + (score.beta - prior.beta) * factor,
    )
