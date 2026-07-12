"""P1 마을 명부 — 멤버십 상태 전이 (TDD).

상태: provisional → member → warned → penalized → excluded (swift trust:
잠정 가입 + 신속 제재). 회복 비용은 위반 이력에 비례 (on-off 방어).
"""

from __future__ import annotations

from app.trust.membership import DEFAULT_POLICY, evaluate_transition


def _t(
    state: str,
    *,
    lower: float,
    obs: float = 10.0,
    violations: int = 0,
) -> str:
    return evaluate_transition(
        state=state,  # type: ignore[arg-type]
        score_lower=lower,
        observations=obs,
        violation_count=violations,
        policy=DEFAULT_POLICY,
    )


def test_provisional_stays_when_insufficient_evidence() -> None:
    # cold start 직후 — 증거 부족이면 낮은 점수라도 제재하지 않음 ("미지")
    assert _t("provisional", lower=0.05, obs=0.0) == "provisional"


def test_provisional_promotes_to_member() -> None:
    assert _t("provisional", lower=0.6) == "member"


def test_member_warned_on_low_score() -> None:
    assert _t("member", lower=0.35) == "warned"


def test_member_penalized_on_very_low_score() -> None:
    assert _t("member", lower=0.2) == "penalized"


def test_excluded_on_violation_threshold() -> None:
    assert (
        _t("member", lower=0.6, violations=DEFAULT_POLICY.exclude_violations)
        == "excluded"
    )


def test_excluded_is_terminal() -> None:
    assert _t("excluded", lower=0.9) == "excluded"


def test_recovery_bar_rises_with_violations() -> None:
    """위반 이력이 있으면 같은 점수로도 member 복귀 불가 — 회복이 비싸다."""
    clean = _t("warned", lower=0.55, violations=0)
    tainted = _t("warned", lower=0.55, violations=3)
    assert clean == "member"
    assert tainted == "warned"


def test_warned_holds_between_thresholds() -> None:
    # warn 임계는 넘었지만 회복 bar 미달 → 유지
    assert _t("warned", lower=0.45) == "warned"


def test_promotion_requires_honesty_evidence() -> None:
    """점수가 높아도 honesty 증거(canary 통과) 없으면 member 불가."""
    blocked = evaluate_transition(
        state="provisional",
        score_lower=0.7,
        observations=10.0,
        violation_count=0,
        honesty_observations=0.0,
        policy=DEFAULT_POLICY,
    )
    allowed = evaluate_transition(
        state="provisional",
        score_lower=0.7,
        observations=10.0,
        violation_count=0,
        honesty_observations=1.0,
        policy=DEFAULT_POLICY,
    )
    assert blocked == "provisional"
    assert allowed == "member"
