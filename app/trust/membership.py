"""마을 명부 — 멤버십 상태 전이 (P1, Ostrom 단계적 제재의 상태 기계).

provisional → member → warned → penalized → excluded.
swift trust 원칙: 가입은 잠정 허용, 제재는 신속. 회복 bar는 위반 이력에
비례해 올라간다 — on-off 공격자의 재기를 비싸게.

순수 함수 — 저장/부수효과 없음. 제재의 *집행*(꾸중 narrative, 가격 할증,
ERC-8004 giveFeedback 미러)은 P4 sanctions.py의 몫.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MembershipState = Literal["provisional", "member", "warned", "penalized", "excluded"]

MEMBERSHIP_STATES: tuple[MembershipState, ...] = (
    "provisional",
    "member",
    "warned",
    "penalized",
    "excluded",
)


@dataclass(frozen=True)
class MembershipPolicy:
    """전이 임계값. 초기값은 plan §3 — trust_sim/운영 데이터로 보정 예정."""

    promote_min_observations: float = 5.0
    promote_min_lower: float = 0.5
    warn_below: float = 0.4
    penalize_below: float = 0.25
    exclude_violations: int = 4
    recovery_penalty_per_violation: float = 0.05


DEFAULT_POLICY = MembershipPolicy()


def evaluate_transition(
    *,
    state: MembershipState,
    score_lower: float,
    observations: float,
    violation_count: int,
    policy: MembershipPolicy = DEFAULT_POLICY,
) -> MembershipState:
    """ledger 스냅샷 기준 다음 멤버십 상태 (선언적 규칙, 위에서부터 우선).

    ① 축출은 종결 — 위반 누적 임계 도달 시에도 축출.
    ② 증거 부족("미지")이면 제재하지 않고 유지.
    ③ 점수 기반 강등 (penalize < warn).
    ④ 회복 — bar는 위반 이력에 비례해 상승.
    """
    if state == "excluded" or violation_count >= policy.exclude_violations:
        return "excluded"
    if observations < policy.promote_min_observations:
        return state
    if score_lower < policy.penalize_below:
        return "penalized"
    if score_lower < policy.warn_below:
        return "warned"
    recovery_bar = (
        policy.promote_min_lower
        + policy.recovery_penalty_per_violation * violation_count
    )
    if score_lower >= recovery_bar:
        return "member"
    return state
