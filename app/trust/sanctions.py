"""단계적 제재 집행 — 상태 → 가격 정책 + 꼰대 꾸중 + ERC-8004 미러 (P4).

Ostrom 단계적 제재 (2차 리서치 §1.3): 꾸중 → 가격 페널티 → 축출.
상태 '판정'은 P1 membership의 몫 — 이 모듈은 판정된 상태의 '집행'만 한다.

꾸중은 결정적 템플릿 v0 (LLM renderer 통합은 EVAL-3 rubric과 함께 후속).
ERC-8004 Reputation 미러는 produce-only — 우리 판정을 발행할 뿐,
온체인 평판을 소비하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from app.storage.trust import get_membership
from app.trust.erc8004 import MockERC8004ReputationRegistry
from app.trust.membership import MembershipState


@dataclass(frozen=True)
class PriceAdjustment:
    buy_multiplier: float  # 매입 단가 배수 (pay-to-share)
    sell_multiplier: float  # 판매 단가 배수 (pay-to-query 할증)
    allowed: bool


_PRICE_POLICY: dict[MembershipState, PriceAdjustment] = {
    # 미지 할인 — 모르는 놈 정보는 싸게 산다 (불확실성-단가 연동)
    "provisional": PriceAdjustment(buy_multiplier=0.5, sell_multiplier=1.0, allowed=True),
    "member": PriceAdjustment(buy_multiplier=1.0, sell_multiplier=1.0, allowed=True),
    "warned": PriceAdjustment(buy_multiplier=0.5, sell_multiplier=1.0, allowed=True),
    "penalized": PriceAdjustment(buy_multiplier=0.25, sell_multiplier=1.5, allowed=True),
    "excluded": PriceAdjustment(buy_multiplier=0.0, sell_multiplier=0.0, allowed=False),
}

_SCOLD_TEMPLATES: dict[MembershipState, str] = {
    "warned": "{agent}, 자네 요즘 하는 말이 영 미덥지 않구먼{cite}. 한 번만 더 그러면 값을 깎겠네.",
    "penalized": "{agent}, 자네한텐 이제 제값 못 쳐주겠네{cite}. 행실부터 고치고 오게.",
    "excluded": "{agent}는 사랑방 출입 금지일세{cite}. 마을 인심을 잃은 게야.",
}

_FEEDBACK_SCORES: dict[MembershipState, int] = {
    "member": 80,
    "provisional": 50,
    "warned": 40,
    "penalized": 20,
    "excluded": 0,
}


@dataclass(frozen=True)
class SanctionDirective:
    agent_id: str
    state: MembershipState
    price: PriceAdjustment
    scold: str | None
    mirrored: bool


def price_adjustment(state: MembershipState) -> PriceAdjustment:
    return _PRICE_POLICY[state]


def scold_line(
    agent_id: str, state: MembershipState, *, cause_ref: str | None = None
) -> str:
    """꼰대 꾸중 발화 (결정적 템플릿). 꾸중에도 근거 citation을 단다."""
    template = _SCOLD_TEMPLATES.get(state)
    if template is None:
        raise ValueError(f"state {state!r} has no scold line")
    cite = f" [↑{cause_ref}]" if cause_ref else ""
    return template.format(agent=agent_id, cite=cite)


def state_to_feedback_score(state: MembershipState) -> int:
    """ERC-8004 giveFeedback score(0-100) 매핑 — 상태 서열과 단조."""
    return _FEEDBACK_SCORES[state]


def apply_sanction_effects(
    conn: duckdb.DuckDBPyConnection,
    *,
    agent_id: str,
    reputation_registry: MockERC8004ReputationRegistry | None = None,
    erc8004_agent_id: int | None = None,
) -> SanctionDirective:
    """현재 멤버십 상태를 읽어 집행 지시를 만든다 (+선택적 온체인 미러).

    명부에 없는 에이전트는 "미지"(provisional) 취급 — 제재도 특혜도 없음.
    """
    member = get_membership(conn, agent_id)
    state: MembershipState = member.state if member else "provisional"
    price = price_adjustment(state)

    scold: str | None = None
    if state in _SCOLD_TEMPLATES:
        row = conn.execute(
            "SELECT trust_event_id FROM trust_events "
            "WHERE agent_id = ? AND positive = FALSE ORDER BY ts DESC LIMIT 1",
            [agent_id],
        ).fetchone()
        cause_ref = str(row[0])[:8] if row else None
        scold = scold_line(agent_id, state, cause_ref=cause_ref)

    mirrored = False
    if reputation_registry is not None and erc8004_agent_id is not None:
        reputation_registry.give_feedback(
            agent_id=erc8004_agent_id,
            score=state_to_feedback_score(state),
            tag=state,
        )
        mirrored = True

    return SanctionDirective(
        agent_id=agent_id, state=state, price=price, scold=scold, mirrored=mirrored
    )
