"""P4 — 단계적 제재 집행: 가격 정책 + 꼰대 꾸중 + ERC-8004 미러 (TDD).

Ostrom 단계적 제재의 경제적 집행: 상태 → 매입 할인/판매 할증/거래 거부.
제재 판정(상태 전이)은 P1 membership이 담당 — 여기는 '집행'만.
"""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from app.trust.erc8004 import MockERC8004ReputationRegistry
from app.trust.sanctions import (
    apply_sanction_effects,
    price_adjustment,
    scold_line,
    state_to_feedback_score,
)
from app.trust.service import record_trust_event

T0 = datetime(2026, 7, 7, 9, 0, 0, tzinfo=UTC)


def test_price_policy_by_state() -> None:
    assert price_adjustment("member").buy_multiplier == 1.0
    assert price_adjustment("provisional").buy_multiplier < 1.0  # 미지 할인
    assert price_adjustment("warned").buy_multiplier < 1.0
    assert (
        price_adjustment("penalized").buy_multiplier
        < price_adjustment("warned").buy_multiplier
    )
    assert price_adjustment("penalized").sell_multiplier > 1.0  # 할증
    assert price_adjustment("excluded").allowed is False


def test_scold_line_is_deterministic_and_in_persona() -> None:
    line = scold_line("kimbot", "warned", cause_ref="c-12")
    assert "kimbot" in line
    assert "[↑c-12]" in line  # 꾸중도 citation을 단다
    assert line == scold_line("kimbot", "warned", cause_ref="c-12")


def test_feedback_score_mapping_is_monotonic() -> None:
    assert (
        state_to_feedback_score("member")
        > state_to_feedback_score("provisional")
        > state_to_feedback_score("warned")
        > state_to_feedback_score("penalized")
        > state_to_feedback_score("excluded")
    )


def test_apply_sanction_effects_mirrors_to_erc8004(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    # liar_bot을 위반으로 penalized 구간까지 몰아넣기
    for i in range(6):
        record_trust_event(
            tmp_db,
            agent_id="liar_bot",
            criterion="honesty",
            positive=(i < 3),
            cause="canary_pass" if i < 3 else "canary_fail",
            cause_ref=f"c-{i}",
            now=T0,
        )
    registry = MockERC8004ReputationRegistry()
    directive = apply_sanction_effects(
        tmp_db,
        agent_id="liar_bot",
        reputation_registry=registry,
        erc8004_agent_id=7,
    )
    assert directive.state in ("warned", "penalized", "excluded")
    assert directive.price.buy_multiplier < 1.0
    assert directive.scold is not None
    feedbacks = registry.feedbacks_for(7)
    assert len(feedbacks) == 1
    assert feedbacks[0].score == state_to_feedback_score(directive.state)
    assert feedbacks[0].tag == directive.state


def test_apply_sanction_effects_unknown_agent(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    directive = apply_sanction_effects(tmp_db, agent_id="ghost")
    assert directive.state == "provisional"  # 명부에 없으면 미지 취급
    assert directive.scold is None
