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
    # member 승격에 요구되는 honesty 증거의 질(quality) — canary로 쌓인 honesty
    # 점수의 now-decay된 mean이 이 값을 초과해야 한다. 증거 '양'(observations)이
    # 아니라 '질'을 봐야, canary 실패(관측량은 늘지만 점수는 낮음)가 게이트를
    # 통과하지 못한다 (F3). 물량 정크(감사 없음)와 whitewash(오래된 감사)도 함께
    # 차단: 감사 없으면 quality 0.0, 오래되면 decay로 prior(0.25) 쪽으로 회귀.
    # 임계 0.3 = prior mean 0.25 + 여유. 감쇠된 pass의 mean은 0.25로 위에서
    # 점근하므로 prior에 딱 맞추면(0.25) stale pass가 아슬히 통과된다. 0.3이면
    # canary 1회 pass가 약 108일 유효 후 만료돼 whitewash가 차단된다.
    promote_min_honesty_quality: float = 0.3


DEFAULT_POLICY = MembershipPolicy()


def evaluate_transition(
    *,
    state: MembershipState,
    score_lower: float,
    observations: float,
    violation_count: int,
    honesty_quality: float | None = None,
    policy: MembershipPolicy = DEFAULT_POLICY,
) -> MembershipState:
    """ledger 스냅샷 기준 다음 멤버십 상태 (선언적 규칙, 위에서부터 우선).

    ① 축출은 종결 — 위반 누적 임계 도달 시에도 축출.
    ② 증거 부족("미지")이면 제재하지 않고 유지.
    ③ 점수 기반 강등 (penalize < warn).
    ④ 회복/승격 — bar는 위반 이력에 비례해 상승. member 승격은 honesty
       증거의 질(now-decay된 honesty mean > prior)을 추가로 요구 — 물량 정크·
       whitewash·감사 실패를 함께 차단. ``honesty_quality=None``은 "정보 없음"
       으로 규칙을 건너뛴다 (순수 함수 단독 사용 시 호출자 책임).
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
        if (
            honesty_quality is not None
            and honesty_quality <= policy.promote_min_honesty_quality
        ):
            return state  # 무지 기준선 넘는 정직 증거 없인 member 없음
        return "member"
    return state
