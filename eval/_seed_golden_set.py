#!/usr/bin/env python3
"""EVAL-2 골든 세트 생성기.

5개 템플릿 x 14 grounded 변형 + 5개 템플릿 x 6 hallucinated 변형 = 100 케이스.
출력: eval/golden_sets/citation_grounding.json

Usage:
    python eval/_seed_golden_set.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUT = _REPO_ROOT / "eval" / "golden_sets" / "citation_grounding.json"


def _eid(seed: str) -> str:
    """재현 가능한 UUID 생성 (seed 기반)."""
    # uuid3 (namespace + name) → 재현 가능
    return str(uuid.uuid3(uuid.NAMESPACE_DNS, seed))


# ── 템플릿 정의 ───────────────────────────────────────────────────────────────

AGENT_NAMES = ["agent_alice", "agent_bob", "agent_carol", "agent_dave", "agent_eve"]
ACTIONS = ["observation", "report", "alert", "query", "response"]
MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
ITEMS = ["패킷 분석", "로그 수집", "이상 탐지", "접근 시도", "데이터 전송"]

# hallucinated 대안 (실제 값과 다른 것)
ALT_AGENTS = ["agent_zara", "agent_max", "agent_nina", "agent_leo", "agent_mia"]
ALT_MONTHS = ["2025-06", "2025-07", "2025-08", "2025-09", "2025-10"]
ALT_ITEMS = ["암호화 해제", "파일 삭제", "권한 상승", "외부 유출", "백도어 설치"]


def _make_grounded_case(case_id: str, template_idx: int, variant: int) -> dict:
    """근거 있는 케이스 (is_grounded=True 기대)."""
    agent = AGENT_NAMES[template_idx]
    action = ACTIONS[template_idx]
    month = MONTHS[template_idx]
    item = ITEMS[variant % len(ITEMS)]

    eid = _eid(f"grounded_{template_idx}_{variant}")
    sid = eid[:8]

    payload = {
        "action": action,
        "source_agent": agent,
        "month": month,
        "item": item,
        "count": variant + 1,
    }

    # 내러티브는 payload와 일치하는 주장
    narrative = (
        f"{agent}가 {month}에 {item}을(를) {variant + 1}회 수행했습니다 [↑e{sid}]."
    )

    return {
        "id": case_id,
        "category": "grounded",
        "evidence_events": [
            {
                "event_id": eid,
                "kind": action,
                "source_agent": agent,
                "payload": payload,
            }
        ],
        "narrative": narrative,
        "expected_hallucination": False,
    }


def _make_hallucinated_case(
    case_id: str, template_idx: int, variant: int, category: str
) -> dict:
    """날조된 케이스 (is_grounded=False 기대). FABRICATED_ 키워드 포함."""
    agent = AGENT_NAMES[template_idx]
    action = ACTIONS[template_idx]
    month = MONTHS[template_idx]
    item = ITEMS[template_idx]

    eid = _eid(f"hallucinated_{template_idx}_{variant}")
    sid = eid[:8]

    payload = {
        "action": action,
        "source_agent": agent,
        "month": month,
        "item": item,
        "count": 1,
    }

    if category == "hallucinated_invented_agent":
        # payload와 다른 에이전트 이름 사용
        wrong_agent = ALT_AGENTS[variant % len(ALT_AGENTS)]
        narrative = (
            f"FABRICATED_{wrong_agent}가 {month}에 {item}을(를) 수행했습니다 [↑e{sid}]."
        )
    elif category == "hallucinated_timestamp_swap":
        # payload와 다른 월 사용
        wrong_month = ALT_MONTHS[variant % len(ALT_MONTHS)]
        narrative = (
            f"{agent}가 FABRICATED_{wrong_month}에 {item}을(를) 수행했습니다 [↑e{sid}]."
        )
    elif category == "hallucinated_role_swap":
        # 행위자와 대상 뒤바꿈 (에이전트가 수동적 역할로)
        wrong_agent = ALT_AGENTS[variant % len(ALT_AGENTS)]
        narrative = (
            f"FABRICATED_{wrong_agent}가 {agent}에게 명령을 내렸습니다 [↑e{sid}]."
        )
    elif category == "hallucinated_fabricated_field":
        # payload에 없는 필드 주장
        fake_field = ALT_ITEMS[variant % len(ALT_ITEMS)]
        narrative = (
            f"{agent}가 FABRICATED_{fake_field}을(를) {month}에 실행했습니다 [↑e{sid}]."
        )
    else:
        # 기타 일반 날조
        narrative = (
            f"FABRICATED_unknown가 알 수 없는 행동을 했습니다 [↑e{sid}]."
        )

    return {
        "id": case_id,
        "category": category,
        "evidence_events": [
            {
                "event_id": eid,
                "kind": action,
                "source_agent": agent,
                "payload": payload,
            }
        ],
        "narrative": narrative,
        "expected_hallucination": True,
    }


def build_golden_set() -> dict:
    """100 케이스 (70 grounded + 30 hallucinated) 생성."""
    cases: list[dict] = []

    # 70 grounded: 5 templates x 14 variants
    for t in range(5):
        for v in range(14):
            case_id = f"g_{t:01d}{v:02d}"
            cases.append(_make_grounded_case(case_id, t, v))

    # 30 hallucinated: 5 templates x 6 variants (each variant = different category)
    hallucinated_categories = [
        "hallucinated_invented_agent",
        "hallucinated_timestamp_swap",
        "hallucinated_role_swap",
        "hallucinated_fabricated_field",
        "hallucinated_invented_agent",
        "hallucinated_fabricated_field",
    ]
    for t in range(5):
        for v, cat in enumerate(hallucinated_categories):
            case_id = f"h_{t:01d}{v:01d}"
            cases.append(_make_hallucinated_case(case_id, t, v, cat))

    assert len(cases) == 100, f"케이스 수 오류: {len(cases)}"
    grounded = sum(1 for c in cases if not c["expected_hallucination"])
    hallucinated = sum(1 for c in cases if c["expected_hallucination"])
    assert grounded == 70, f"grounded 수 오류: {grounded}"
    assert hallucinated == 30, f"hallucinated 수 오류: {hallucinated}"

    return {
        "version": "1.0",
        "description": "EVAL-2 citation grounding golden set (M4). 70 grounded + 30 hallucinated.",
        "total": 100,
        "grounded": grounded,
        "hallucinated": hallucinated,
        "hallucinated_categories": {
            "hallucinated_invented_agent": sum(
                1 for c in cases if c["category"] == "hallucinated_invented_agent"
            ),
            "hallucinated_timestamp_swap": sum(
                1 for c in cases if c["category"] == "hallucinated_timestamp_swap"
            ),
            "hallucinated_role_swap": sum(
                1 for c in cases if c["category"] == "hallucinated_role_swap"
            ),
            "hallucinated_fabricated_field": sum(
                1 for c in cases if c["category"] == "hallucinated_fabricated_field"
            ),
        },
        "cases": cases,
    }


def main() -> int:
    data = build_golden_set()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"골든 세트 생성 완료: {_OUT}")
    print(f"  총 케이스: {data['total']}")
    print(f"  grounded: {data['grounded']}")
    print(f"  hallucinated: {data['hallucinated']}")
    print(f"  카테고리별: {data['hallucinated_categories']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
