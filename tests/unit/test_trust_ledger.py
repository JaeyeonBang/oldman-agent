"""P1 Trust Ledger — Beta 점수 + 비대칭 동역학 + 시간 감쇠 (TDD).

핵심 성질 (research/agent-trust-impl-plan-2026-07.md §3 P1):
  - cold start = 낮은 prior + 높은 불확실성 ("미지" ≠ "중립")
  - 비대칭: 느리게 오르고 빠르게 떨어짐 (on-off 방어)
  - 감쇠: 증거가 prior로 회귀 (최근 행동이 지배)
"""

from __future__ import annotations

import pytest

from app.trust.ledger import (
    COLD_START_PRIOR,
    DEFAULT_POLICY,
    BetaScore,
    decay,
    update,
)


def test_cold_start_is_low_and_uncertain() -> None:
    s = COLD_START_PRIOR
    assert s.mean < 0.5  # 중립(0.5)이 아니라 낮게 시작 — whitewashing 차단
    assert s.lower_bound() < 0.2  # 불확실성 반영 시 더 낮음
    assert s.std > 0.1  # "미지" — 높은 불확실성


def test_mean_and_bounds_math() -> None:
    s = BetaScore(alpha=8.0, beta=2.0)
    assert s.mean == pytest.approx(0.8)
    assert 0.0 <= s.lower_bound() < s.mean


def test_positive_updates_raise_mean_slowly() -> None:
    s = COLD_START_PRIOR
    for _ in range(5):
        s = update(s, positive=True, policy=DEFAULT_POLICY)
    assert s.mean > COLD_START_PRIOR.mean
    assert s.mean < 0.9  # 5번 잘했다고 바로 신뢰 만점 아님


def test_asymmetry_one_negative_outweighs_one_positive() -> None:
    """비대칭 동역학: 부정 증거 1회가 긍정 증거 1회보다 |Δmean| 크게 움직임."""
    base = BetaScore(alpha=6.0, beta=4.0)
    up = update(base, positive=True, policy=DEFAULT_POLICY)
    down = update(base, positive=False, policy=DEFAULT_POLICY)
    assert abs(down.mean - base.mean) > abs(up.mean - base.mean)


def test_weight_scales_update() -> None:
    base = BetaScore(alpha=4.0, beta=4.0)
    small = update(base, positive=True, weight=1.0, policy=DEFAULT_POLICY)
    big = update(base, positive=True, weight=5.0, policy=DEFAULT_POLICY)
    assert big.mean > small.mean  # 거래액 가중


def test_decay_moves_toward_prior() -> None:
    strong = BetaScore(alpha=50.0, beta=5.0)
    decayed = decay(strong, elapsed_days=30.0, half_life_days=30.0)
    # 반감기 1회 경과 → prior 방향으로 절반 회귀
    assert decayed.alpha == pytest.approx(
        COLD_START_PRIOR.alpha + (strong.alpha - COLD_START_PRIOR.alpha) * 0.5
    )
    assert decayed.mean < strong.mean
    assert decayed.std > strong.std  # 오래되면 불확실성 회복


def test_decay_zero_elapsed_is_identity() -> None:
    s = BetaScore(alpha=10.0, beta=3.0)
    d = decay(s, elapsed_days=0.0, half_life_days=30.0)
    assert d.alpha == pytest.approx(s.alpha)
    assert d.beta == pytest.approx(s.beta)


def test_observations_counts_evidence_mass() -> None:
    s = COLD_START_PRIOR
    assert s.observations == pytest.approx(0.0)
    s2 = update(s, positive=True, policy=DEFAULT_POLICY)
    assert s2.observations > 0.0
