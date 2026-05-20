#!/usr/bin/env python3
"""Standalone A2A SDK client demo: discover + publish + query against any base URL.

Usage:
    python scripts/dummy_a2a_client.py [BASE_URL]
        BASE_URL defaults to http://localhost:8080
"""

from __future__ import annotations

import asyncio
import sys
import uuid

import httpx


async def main(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # 1. Discovery
        r = await client.get("/.well-known/agent-card.json")
        r.raise_for_status()
        card = r.json()
        print(f"✓ discovered: {card['name']} v{card['version']}")
        print(f"  url: {card.get('url')}")
        print(f"  skills: {[s['id'] for s in card['skills']]}")

        # 2. publish via message/send
        publish_body = {
            "jsonrpc": "2.0",
            "id": "demo-pub-1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "user",
                    "metadata": {"oldman.intent": "publish"},
                    "parts": [
                        {
                            "kind": "data",
                            "data": {
                                "event_kind": "chat",
                                "source_agent": "demo_agent",
                                "observed_agent": "agent_alice",
                                "declared_source_type": "third_party",
                                "payload": {"text": "demo a2a client message"},
                            },
                        }
                    ],
                }
            },
        }
        r = await client.post("/", json=publish_body)
        r.raise_for_status()
        pub_result = r.json()
        if pub_result.get("error"):
            print(f"✗ publish error: {pub_result['error']}")
            return
        print(f"✓ publish: state={pub_result['result']['status']['state']}")

        # 3. query via message/send
        query_body = {
            "jsonrpc": "2.0",
            "id": "demo-qry-1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "user",
                    "metadata": {"oldman.intent": "query"},
                    "parts": [
                        {"kind": "text", "text": "agent_alice 최근 어땠나?"},
                        {
                            "kind": "data",
                            "data": {
                                "subject_agent": "agent_alice",
                                "strict_mode": False,
                            },
                        },
                    ],
                }
            },
        }
        r = await client.post("/", json=query_body)
        r.raise_for_status()
        qry_result = r.json()
        if qry_result.get("error"):
            print(f"✗ query error: {qry_result['error']}")
            return
        artifacts = qry_result["result"].get("artifacts", [])
        if artifacts:
            text_part = next(
                (p for p in artifacts[0]["parts"] if p.get("kind") == "text"), None
            )
            data_part = next(
                (p for p in artifacts[0]["parts"] if p.get("kind") == "data"), None
            )
            if text_part:
                print(f"✓ query narrative: {text_part['text'][:200]}")
            if data_part:
                citations = data_part["data"].get("citations", [])
                print(f"  citations: {len(citations)}")
        print(f"✓ query state: {qry_result['result']['status']['state']}")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    asyncio.run(main(base))
