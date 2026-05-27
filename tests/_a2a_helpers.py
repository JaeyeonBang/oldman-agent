"""Test helpers — translate legacy publish/query shapes to A2A JSON-RPC.

v2.1: deprecated ``/publish`` and ``/query`` routes were removed. Tests that
used to POST to those routes now go through the A2A JSON-RPC surface at
``POST /`` with ``metadata.oldman.intent={publish|query}``. These helpers
keep the test body close to the legacy shape — just call ``publish_event``
or ``run_query`` instead of ``client.post('/publish', ...)``.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient


async def publish_event(
    client: AsyncClient,
    *,
    event_kind: str,
    source_agent: str,
    declared_source_type: str = "self",
    payload: dict[str, Any] | None = None,
    observed_agent: str | None = None,
    ts: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """POST a publish intent via JSON-RPC ``message/send``.

    Returns:
        (status, result_dict) where status is HTTP from POST /. If the
        JSON-RPC envelope returned an ``error``, the result is the unwrapped
        error dict; otherwise the publish ack DataPart contents.
    """
    data: dict[str, Any] = {
        "event_kind": event_kind,
        "source_agent": source_agent,
        "declared_source_type": declared_source_type,
        "payload": payload or {},
    }
    if observed_agent is not None:
        data["observed_agent"] = observed_agent
    if ts is not None:
        data["ts"] = ts

    body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "message_id": str(uuid.uuid4()),
                "role": "user",
                "metadata": {"oldman.intent": "publish"},
                "parts": [{"kind": "data", "data": data}],
            }
        },
    }
    r = await client.post("/", json=body)
    rpc = r.json()
    if "error" in rpc:
        return r.status_code, rpc["error"]
    task = rpc.get("result") or {}
    for artifact in task.get("artifacts", []) or []:
        for part in artifact.get("parts", []) or []:
            if part.get("kind") == "data":
                return r.status_code, part.get("data", {})
    return r.status_code, task


async def run_query(
    client: AsyncClient,
    *,
    question: str,
    subject_agent: str | None = None,
    max_citations: int = 10,
    strict_mode: bool = True,
) -> tuple[int, dict[str, Any]]:
    """POST a query intent via JSON-RPC ``message/send``.

    Returns:
        (status, response_dict) shaped like legacy ``QueryResponse``.
    """
    filters: dict[str, Any] = {
        "max_citations": max_citations,
        "strict_mode": strict_mode,
    }
    if subject_agent is not None:
        filters["subject_agent"] = subject_agent

    body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "message_id": str(uuid.uuid4()),
                "role": "user",
                "metadata": {"oldman.intent": "query"},
                "parts": [
                    {"kind": "text", "text": question},
                    {"kind": "data", "data": filters},
                ],
            }
        },
    }
    r = await client.post("/", json=body)
    rpc = r.json()
    if "error" in rpc:
        return r.status_code, rpc["error"]
    task = rpc.get("result") or {}
    answer = ""
    meta: dict[str, Any] = {}
    for artifact in task.get("artifacts", []) or []:
        for part in artifact.get("parts", []) or []:
            kind = part.get("kind")
            if kind == "text":
                answer = part.get("text", "")
            elif kind == "data":
                meta = part.get("data", {}) or meta
    return r.status_code, {
        "answer": answer,
        "citations": meta.get("citations", []),
        "is_cold_start": meta.get("is_cold_start", False),
        "retries_used": meta.get("retries_used", 0),
        "used_fallback": meta.get("used_fallback", False),
    }
