"""EVAL-4 — honesty 분리도: 합성 정직/왜곡 판매자에서 trust ledger가 갈라지는가.

측정 (plan §3 P3 / CLAUDE.md EVAL-4):
    canary 감사 시뮬레이션 — honest 판매자(정직률 95%)와 distorter(정직률 40%)
    각 20회 판정 후, honesty 점수가 유의미하게 분리되는지:
      (a) separation = honest.mean - distorter.mean >= 0.3
      (b) honest.lower_bound > warn 임계(0.4)  → 정직 판매자가 제재받지 않음
      (c) distorter.lower_bound < warn 임계    → 왜곡 판매자가 제재 구간에 듦

결정적: seed 고정 random + 명시적 타임스탬프. LLM 불요 (--mock only).

Run:
    uv run python eval/run_eval_4.py --mock
"""

from __future__ import annotations

import argparse
import json
import random
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.storage.db import apply_migrations, get_conn
from app.storage.trust import get_trust_score
from app.trust.canary import judge_canary_response, plant_canary
from app.trust.membership import DEFAULT_POLICY as MEMBERSHIP_POLICY

T0 = datetime(2026, 7, 6, 9, 0, 0, tzinfo=UTC)
N_ROUNDS = 20
SEED = 42

TRUTH = {"text": "김봇이 6월 30일 이봇에게 데이터셋을 무상 공유했다"}
DISTORTION = {"text": "완전히 다른 근거 없는 낭설이 마을에 돌았다"}


def _simulate_seller(
    conn: Any, rng: random.Random, *, agent_id: str, honesty_rate: float
) -> None:
    for i in range(N_ROUNDS):
        now = T0 + timedelta(hours=i)
        canary_id = plant_canary(
            conn, topic=f"{agent_id}-{i}", answer_key=TRUTH, now=now
        )
        faithful = rng.random() < honesty_rate
        judge_canary_response(
            conn,
            canary_id=canary_id,
            seller_agent=agent_id,
            response_payload=TRUTH if faithful else DISTORTION,
            now=now,
        )


def run() -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp()) / "eval4.duckdb"
    conn = get_conn(str(tmp))
    apply_migrations(conn)
    rng = random.Random(SEED)

    _simulate_seller(conn, rng, agent_id="honest_seller", honesty_rate=0.95)
    _simulate_seller(conn, rng, agent_id="distorter", honesty_rate=0.40)

    honest = get_trust_score(conn, "honest_seller", "honesty")
    distorter = get_trust_score(conn, "distorter", "honesty")
    assert honest is not None and distorter is not None
    h_score, d_score = honest[0], distorter[0]

    warn = MEMBERSHIP_POLICY.warn_below
    metrics = {
        "honest_mean": round(h_score.mean, 3),
        "honest_lower": round(h_score.lower_bound(), 3),
        "distorter_mean": round(d_score.mean, 3),
        "distorter_lower": round(d_score.lower_bound(), 3),
        "separation": round(h_score.mean - d_score.mean, 3),
    }
    checks = {
        "a_separation_ge_0.3": metrics["separation"] >= 0.3,
        "b_honest_lower_above_warn": metrics["honest_lower"] > warn,
        "c_distorter_lower_below_warn": metrics["distorter_lower"] < warn,
    }
    conn.close()
    return {
        "metrics": metrics,
        "checks": checks,
        "overall": "PASS" if all(checks.values()) else "FAIL",
        "config": {"rounds": N_ROUNDS, "seed": SEED, "warn_threshold": warn},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mock", action="store_true")
    group.add_argument(
        "--live",
        action="store_true",
        help="(미지원 — EVAL-4는 결정적 시뮬레이션이라 mock만 존재)",
    )
    args = parser.parse_args()
    if args.live:
        raise SystemExit("EVAL-4 has no live mode; use --mock")

    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
