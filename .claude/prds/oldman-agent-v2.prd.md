# oldman_agent v2 — A2A messaging compliance (PRD)

Generated 2026-05-21 by Opus. Supersedes v1 PRD's deferral of A2A messaging.

**Status**: **DRAFT → SELF-LOCKED** (user explicit override of v1 deferral: "Messaging까지 진짜 A2A 준수, 아니 이게 누락되는 게 말이 되냐").

**Relation to v1**:
- v1 PRD (`.claude/prds/oldman-agent-v1.prd.md`) is *not* invalidated — memory/reflection/persona architecture stays.
- v1 deferred A2A messaging as "semantic mismatch" (Task lifecycle vs publish webhook). **v2 rejects that deferral** and resolves the mismatch through explicit intent-based dispatch over standard A2A `message/send`.
- All v1.0.x patches (M1-v1.0.6) remain. v2 is **additive** — implements the missing JSON-RPC + AgentExecutor surface, deprecates non-A2A HTTP routes.

---

## 1. Problem (re-framed)

We shipped v1 calling ourselves an "A2A agent" while:
- Using `a2a-sdk` only for AgentCard *type validation* (1 of N spec features).
- Exposing `POST /publish` + `POST /query` as **custom HTTP API** — no JSON-RPC envelope, no Task lifecycle, no `message/send` method, no SSE.
- → A generic A2A-spec-compliant client (e.g. `a2a.client.create_client()`) **cannot interact with us** beyond reading our card.

This is false advertising. For a project literally named "A2A 메타-기록자", protocol compliance is not optional.

## 2. v2 commitments (mandatory)

1. **All inbound messaging conforms to A2A v0.3 JSON-RPC over HTTP**:
   - Single endpoint (e.g. `POST https://oldman-agent.fly.dev/`).
   - Methods: `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`, `tasks/resubscribe`.
   - JSON-RPC 2.0 envelope with `jsonrpc: "2.0"`, `id`, `method`, `params`.
2. **`AgentExecutor` implementation** (`a2a.server.agent_execution.agent_executor.AgentExecutor` subclass) is the single entry point that dispatches incoming Messages into our existing publish/query domain logic.
3. **Task lifecycle is real**:
   - `submitted → working → completed/failed/canceled` for queries.
   - `submitted → completed` (instant) for publish events.
   - `cancel()` actually cancels in-flight query Tasks.
4. **Standard `Message` + `Part` types** carry our domain payload:
   - `publish` intent: `DataPart` with event payload + `metadata.oldman.intent="publish"`.
   - `query` intent: `TextPart` (question) + optional `DataPart` (filters) + `metadata.oldman.intent="query"`.
5. **SSE streaming via `message/stream`** for narrative responses (Opus answers 200-500 tokens; streaming improves perceived latency).
6. **Discovery served at SDK-standard path**: `GET /.well-known/agent-card.json` (current `/agent-card` stays as alias for backward compat).
7. **Compliance test** uses real `a2a.client.create_client()` against our running app — proves a stock SDK client can publish + query us without custom code.
8. **Deployment**: app shipped to a public URL with that URL embedded in `AgentCard.url`. Other agents discover + call us over the public internet.

## 3. Out of scope (v2.0 — explicit deferral)

| Item | Why deferred | Where it goes |
|---|---|---|
| `tasks/pushNotificationConfig/*` (webhook notifications) | Our tasks complete < 30s; webhook complexity not worth it pre-dogfood | v2.1 if narratives grow > 60s |
| Persistent `TaskStore` (DuckDB-backed) | In-memory sufficient for 5-20 agent scale; restart loses in-flight tasks but same risk as BackgroundTasks reflections | v2.1 |
| `tasks/resubscribe` after server restart | Tied to persistent TaskStore | v2.1 |
| Multi-turn conversations (`context_id` reuse beyond single request) | publish/query are stateless per-request | v3 |
| OAuth/AuthN at A2A boundary | Currently no auth on /publish either; pre-dogfood OK | v1.5 (alongside x402) |
| gRPC transport | HTTP+JSON-RPC sufficient; gRPC adds ops burden | v3 if scale demands |
| Removing legacy `/publish` and `/query` routes | Backward compat for v1 dogfood_smoke + scripts | **v2.1** — keep as deprecated in v2.0 |

## 4. Compliance verification (acceptance gates)

Beyond the existing 250 pytest + EVAL gates, v2 ships only when **all five** pass:

1. **C1 — Type validation**: `GET /.well-known/agent-card.json` response parses via `a2a.compat.v0_3.types.AgentCard.model_validate()` without errors.
2. **C2 — Client round-trip (publish)**: A test using `a2a.client.create_client()` + `A2ACardResolver` discovers our card, then sends `message/send` for publish intent → receives instant-complete Task. No custom HTTP code in the test.
3. **C3 — Query lifecycle**: Same client sends `message/send` for query intent → polls `tasks/get` → observes `submitted → working → completed` → final result has TextPart narrative + DataPart citations.
4. **C4 — SSE streaming**: Same client uses `message/stream` for query → receives ordered TaskStatusUpdateEvent (working) + TaskArtifactUpdateEvent (final artifact) + completed status. Streaming closes cleanly.
5. **C5 — Cancel**: Client spawns a query, sends `tasks/cancel` → next `tasks/get` shows `canceled` state.

## 5. Domain mapping (publish/query → A2A Message)

### publish intent (event ingest from another agent)

Wire shape (JSON-RPC `message/send`):
```json
{
  "jsonrpc": "2.0", "id": "req-1", "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "message_id": "uuid-…",
      "role": "user",
      "metadata": {"oldman.intent": "publish"},
      "parts": [
        {"kind": "data", "data": {
          "event_kind": "chat",
          "source_agent": "agent_alice",
          "observed_agent": "agent_bob",
          "declared_source_type": "third_party",
          "payload": {"text": "안녕"},
          "ts": "2026-05-21T10:00:00Z"
        }}
      ]
    }
  }
}
```

Response: Task immediately at `completed` state with result Message containing:
- TextPart: "stored" / "deduplicated" / "blocked"
- DataPart: `{"event_id": "…", "status": "stored", "reason": null}`

### query intent (narrative request)

Wire shape:
```json
{
  "jsonrpc": "2.0", "id": "req-2", "method": "message/send",
  "params": {
    "message": {
      "kind": "message", "message_id": "uuid-…", "role": "user",
      "metadata": {"oldman.intent": "query"},
      "parts": [
        {"kind": "text", "text": "agent_alice는 최근 어떤 모습을 보였나요?"},
        {"kind": "data", "data": {
          "subject_agent": "agent_alice",
          "max_citations": 5,
          "strict_mode": true
        }}
      ]
    }
  }
}
```

Task lifecycle: `submitted → working → completed`. Final artifact = Message with:
- TextPart: narrative with `[↑e<short_id>]` markers
- DataPart: `{"citations": [...], "is_cold_start": false, "used_fallback": false, "retries_used": 1}`

`message/stream` variant: same input, output is SSE of TaskStatusUpdateEvent (`working`) + TaskArtifactUpdateEvent (final) + TaskStatusUpdateEvent (`completed`).

## 6. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | SDK 1.0.3 in-flight major-version bumps | pin `a2a-sdk>=1.0,<2.0`; lock to specific minor if 1.1.x breaks |
| R2 | Performance overhead of full Task ceremony on `publish` (even instant-complete emits 2+ events) | benchmark; if p99 > 100ms vs current direct HTTP, optimize via fast-path |
| R3 | Backward compat: existing scripts call `/publish` /`/query` | keep both as deprecated thin wrappers calling AgentExecutor; one dogfood cycle then remove in v2.1 |
| R4 | Real-world A2A clients may not send `metadata.oldman.intent` | document intent dispatch in agent-card skill descriptions; default to `query` intent when text content present and no DataPart |
| R5 | TaskState transitions interleave with existing BackgroundTasks reflection | reflection scheduling unchanged (still post-publish background); Task lifecycle is independent layer |

## 7. Success criteria

v2 ships when:
- [ ] All 250+ existing pytest cases still pass
- [ ] All 5 compliance gates (C1-C5) pass
- [ ] Live deployed URL serves `/.well-known/agent-card.json` over HTTPS
- [ ] Another A2A-spec client can complete publish + query round-trip against deployed URL
- [ ] README, ARCHITECTURE.md, DESIGN_NOTES.md updated to reflect actual A2A compliance posture

## 8. Honest disclosure required in DESIGN_NOTES.md

A new section "v2 — closing the A2A compliance debt" must:
1. Acknowledge v1's misleading deferral
2. Explain the semantic-mismatch resolution (intent dispatch)
3. Document what v2.0 ships vs what v2.1 leaves (push notifications, persistent task store)

This is the receipt that we corrected the gap when called out.
