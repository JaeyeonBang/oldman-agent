#!/usr/bin/env python3
"""Manual smoke — publish a single event against a running oldman_agent.

Usage:
    uvicorn app.main:create_app --factory --port 8080 --workers 1  &
    python scripts/dummy_publish.py
"""

from __future__ import annotations

import sys

import httpx

BASE_URL = "http://localhost:8080"


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        h = client.get("/health")
        print(f"GET /health → {h.status_code} {h.json()}")
        c = client.get("/agent-card")
        print(f"GET /agent-card → {c.status_code} (persona={c.json()['x-oldman']['persona']})")
        p = client.post(
            "/publish",
            json={
                "event_kind": "chat",
                "source_agent": "dummy_agent",
                "observed_agent": "agent_bob",
                "declared_source_type": "third_party",
                "payload": {"text": "안녕, 동네 사랑방 첫 손님이오"},
            },
        )
        print(f"POST /publish → {p.status_code} {p.json()}")
        return 0 if p.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
