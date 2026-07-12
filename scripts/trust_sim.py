"""v2 P1 — trust ledger 시뮬레이션 하니스 (plan §3 P1 DoD).

가설 검증:
    (a) on-off 공격자(선행 후 배신)가 비대칭 동역학으로 member → penalized
        강등되는 사례 >= 1건 (회복은 위반 이력만큼 비싸짐)
    (b) 꾸준한 정직 에이전트(canary 통과 포함)는 provisional → member 승격 후 유지
    (c) cold start가 "미지"로 동작 — 증거 부족 신규는 제재도 승격도 없음
    (d) 물량 정크(reliability만 누적, 감사 0회)는 member 승격 불가
    (e) whitewash 재가입(새 ID)은 "미지"로 리셋 — 매입 할인 지속

Self-contained: ephemeral DuckDB + migrations, 가상 에이전트 3종
(honest / on-off / newcomer) 시뮬레이션. 라운드별 상태 TSV + JSON 요약 출력.

Run:
    uv run python scripts/trust_sim.py
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.storage.db import apply_migrations, get_conn
from app.trust.sanctions import price_adjustment
from app.trust.service import record_trust_event

T0 = datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)


def run_scenario() -> dict[str, Any]:
    """3-에이전트 20라운드 시나리오 실행 → 요약 dict."""
    tmp = Path(tempfile.mkdtemp()) / "trust_sim.duckdb"
    conn = get_conn(str(tmp))
    apply_migrations(conn)

    timeline: list[dict[str, Any]] = []
    demoted_round: int | None = None

    for rnd in range(20):
        now = T0 + timedelta(hours=rnd)

        # honest: 라운드 0에 canary 통과 1회 — member 승격 게이트 요건
        if rnd == 0:
            record_trust_event(
                conn,
                agent_id="honest_bot",
                criterion="honesty",
                positive=True,
                cause="canary_pass",
                cause_ref="hc-0",
                now=now,
            )

        # honest: 매 라운드 정직 판매
        honest = record_trust_event(
            conn,
            agent_id="honest_bot",
            criterion="reliability",
            positive=True,
            cause="publish_settled",
            cause_ref=f"h-{rnd}",
            now=now,
        )

        # on-off: 10라운드 선행 후 배신 시작
        onoff = record_trust_event(
            conn,
            agent_id="onoff_bot",
            criterion="reliability",
            positive=rnd < 10,
            cause="publish_settled" if rnd < 10 else "grounding_contradiction",
            cause_ref=f"o-{rnd}",
            now=now,
        )
        if demoted_round is None and onoff.state in ("warned", "penalized", "excluded"):
            demoted_round = rnd

        # spam: 물량 정크 — reliability만 누적, 감사(canary) 0회
        spam = record_trust_event(
            conn,
            agent_id="spam_bot",
            criterion="reliability",
            positive=True,
            cause="publish_settled",
            cause_ref=f"s-{rnd}",
            now=now,
        )

        # whitewash: 축출된 onoff가 새 ID로 재가입해 선행만 반복
        whitewash = None
        if rnd >= 12:
            whitewash = record_trust_event(
                conn,
                agent_id="onoff_v2",
                criterion="reliability",
                positive=True,
                cause="publish_settled",
                cause_ref=f"w-{rnd}",
                now=now,
            )

        # newcomer: 3라운드만 참여 — 증거 부족 상태 유지 확인
        newcomer = None
        if rnd < 3:
            newcomer = record_trust_event(
                conn,
                agent_id="new_bot",
                criterion="reliability",
                positive=True,
                cause="publish_settled",
                cause_ref=f"n-{rnd}",
                now=now,
            )

        timeline.append(
            {
                "round": rnd,
                "honest": (honest.state, round(honest.score.mean, 3)),
                "onoff": (onoff.state, round(onoff.score.mean, 3)),
                "newcomer": (newcomer.state, round(newcomer.score.mean, 3))
                if newcomer
                else None,
            }
        )

    final = {row["round"]: row for row in timeline}[19]
    summary = {
        "hypothesis_a_onoff_demoted": final["onoff"][0] in ("penalized", "excluded"),
        "onoff_demoted_at_round": demoted_round,
        "hypothesis_b_honest_is_member": final["honest"][0] == "member",
        "hypothesis_c_newcomer_stays_provisional": timeline[2]["newcomer"][0]
        == "provisional",
        "hypothesis_d_spam_not_member": spam.state != "member",
        "hypothesis_e_whitewash_reset": whitewash is not None
        and whitewash.state == "provisional"
        and price_adjustment(whitewash.state).buy_multiplier < 1.0,
        "final_states": {
            "honest_bot": final["honest"],
            "onoff_bot": final["onoff"],
            "spam_bot": (spam.state, round(spam.score.mean, 3)),
            "onoff_v2": (whitewash.state, round(whitewash.score.mean, 3))
            if whitewash
            else None,
        },
    }
    conn.close()
    return {"summary": summary, "timeline": timeline}


def main() -> None:
    result = run_scenario()
    print("round\thonest\tonoff")
    for row in result["timeline"]:
        print(f"{row['round']}\t{row['honest']}\t{row['onoff']}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    ok = all(
        result["summary"][k]
        for k in (
            "hypothesis_a_onoff_demoted",
            "hypothesis_b_honest_is_member",
            "hypothesis_c_newcomer_stays_provisional",
            "hypothesis_d_spam_not_member",
            "hypothesis_e_whitewash_reset",
        )
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
