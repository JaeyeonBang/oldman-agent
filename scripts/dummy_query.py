#!/usr/bin/env python3
"""Manual smoke — query narrative against a running oldman_agent.

Usage:
    # 1. Start the server (with ANTHROPIC_API_KEY set for real LLM, or mock provider):
    uvicorn app.main:create_app --factory --port 8080 --workers 1 &

    # 2. Seed some events first:
    python scripts/dummy_publish.py

    # 3. Query:
    python scripts/dummy_query.py
    python scripts/dummy_query.py --agent agent_alice
    python scripts/dummy_query.py --question "최근 에이전트들 동향은?"

Notes:
    - 503 response means narrative_provider is not configured on app.state.
      In production, set ANTHROPIC_API_KEY and restart.
    - Cold-start (empty DB) returns fallback message with is_cold_start=true.
    - Citations are [↑e<short_id>] markers resolved to event_ids.
"""

from __future__ import annotations

import argparse
import sys

import httpx

BASE_URL = "http://localhost:8080"


def main() -> int:
    parser = argparse.ArgumentParser(description="Query oldman_agent narrative endpoint")
    parser.add_argument(
        "--question",
        default="최근 에이전트들은 어떤 활동을 했나요?",
        help="질문 텍스트 (기본: 소사이어티 전체 동향)",
    )
    parser.add_argument(
        "--agent",
        default=None,
        help="대상 에이전트 이름 (생략 시 전체 소사이어티)",
    )
    parser.add_argument(
        "--max-citations",
        type=int,
        default=10,
        help="최대 인용 수 (기본: 10)",
    )
    args = parser.parse_args()

    body: dict = {
        "question": args.question,
        "max_citations": args.max_citations,
    }
    if args.agent:
        body["subject_agent"] = args.agent

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        # 서버 상태 확인
        h = client.get("/health")
        if h.status_code != 200:
            print(f"서버 응답 없음: GET /health → {h.status_code}", file=sys.stderr)
            return 1
        print(f"GET /health → {h.status_code} {h.json()}")

        # 쿼리 실행
        print("\nPOST /query")
        print(f"  question: {body['question']}")
        if args.agent:
            print(f"  subject_agent: {args.agent}")

        r = client.post("/query", json=body)
        print(f"\n→ status: {r.status_code}")

        if r.status_code == 503:
            detail = r.json().get("detail", {})
            print(f"  503 {detail.get('reason', 'unknown')}")
            print("  narrative_provider 가 설정되지 않았습니다. ANTHROPIC_API_KEY 확인 후 재시작.")
            return 1

        if r.status_code != 200:
            print(f"  오류: {r.text}", file=sys.stderr)
            return 1

        data = r.json()
        print(f"  is_cold_start: {data['is_cold_start']}")
        print(f"  used_fallback: {data['used_fallback']}")
        print(f"  retries_used: {data['retries_used']}")
        print(f"  citations ({len(data['citations'])}개):")
        for c in data["citations"]:
            event_id_display = c.get("event_id") or c["short_id"]
            print(f"    [↑e{c['short_id']}] → {event_id_display}")
        print(f"\n답변:\n{data['answer']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
