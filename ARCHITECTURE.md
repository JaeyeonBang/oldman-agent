# oldman_agent — Architecture

Generated 2026-05-21 (v2 — A2A messaging compliance baked in).

## At a glance

```
┌──────────────────────────────────────────────────────────────────────────┐
│ External A2A clients (stock a2a.client.create_client)                    │
└──────────────┬──────────────────────────────────────────┬────────────────┘
               │ GET /.well-known/agent-card.json         │ POST / (JSON-RPC 2.0)
               │ (discovery)                              │ method: message/send |
               │                                          │ message/stream |
               ▼                                          │ tasks/get | tasks/cancel
   ┌──────────────────────┐                               │ tasks/resubscribe
   │ AgentCard (A2A v0.3) │                               │
   │   url: https://...   │                               ▼
   │   skills:            │              ┌────────────────────────────────┐
   │   - publish_event    │              │ JsonRpcDispatcher (SDK)        │
   │   - narrative_query  │              │   parses JSON-RPC envelope     │
   │   x-oldman:          │              │   validates v0.3 method names  │
   │     persona, ...     │              └──────────┬─────────────────────┘
   └──────────────────────┘                         │
                                                    ▼
                                  ┌──────────────────────────────────────┐
                                  │ DefaultRequestHandlerV2 (SDK)        │
                                  │   on_message_send → executor.execute │
                                  │   on_message_send_stream → SSE       │
                                  │   on_cancel_task → executor.cancel   │
                                  │   on_get_task → TaskStore.get        │
                                  └──────────┬───────────────────────────┘
                                             │
                                             ▼
                          ┌────────────────────────────────────────────┐
                          │ OldmanAgentExecutor (we implement)         │
                          │   execute(ctx, queue):                     │
                          │     intent = ctx.message.metadata          │
                          │              .get("oldman.intent")         │
                          │     if intent == "publish":                │
                          │       → dispatch_publish(...)              │
                          │       → emit instant-complete Task         │
                          │     elif intent == "query":                │
                          │       → emit Task(submitted)               │
                          │       → emit TaskStatusUpdateEvent(working)│
                          │       → render narrative (M3 path)         │
                          │       → emit TaskArtifactUpdateEvent       │
                          │       → emit TaskStatusUpdateEvent(completed)│
                          │   cancel(ctx, queue):                      │
                          │     cancel asyncio task + emit canceled    │
                          └──────────┬─────────────────────────────────┘
                                     │
            ┌────────────────────────┼─────────────────────────┐
            ▼                        ▼                         ▼
   ┌────────────────┐     ┌────────────────────┐     ┌──────────────────┐
   │ dispatch_publish│     │ render_narrative   │     │ BackgroundTasks  │
   │ (M1 path):      │     │ (M3 path):         │     │ reflection       │
   │  validate +     │     │  select_evidence + │     │ scheduler        │
   │  blocklist +    │     │  build_prompt +    │     │ (unchanged)      │
   │  jaccard +      │     │  provider.complete │     │                  │
   │  insert TX      │     │  + validator       │     │                  │
   └────────┬────────┘     │  (existence|judge) │     └──────────────────┘
            │              └────────┬───────────┘
            │                       │
            ▼                       ▼
   ┌────────────────────────────────────────────────┐
   │ DuckDB single-file (workers=1)                 │
   │   events / entities_episodic / entities_semantic│
   │   / reflections (+ _schema_version)            │
   └────────────────────────────────────────────────┘
```

## A2A protocol surface (v0.3 wire)

| Wire method | Handler | Behavior |
|---|---|---|
| `message/send` w/ `intent="publish"` + DataPart | OldmanAgentExecutor.execute | Validate + dedup + persist → emit instant-complete Task with ack Message |
| `message/send` w/ `intent="query"` + TextPart [+ DataPart filters] | OldmanAgentExecutor.execute | Spawn Task; lifecycle submitted→working→completed; final artifact = Message(TextPart narrative + DataPart citations) |
| `message/stream` w/ `intent="query"` | OldmanAgentExecutor.execute | Same as above but SSE: TaskStatusUpdateEvent(working) → TaskArtifactUpdateEvent → TaskStatusUpdateEvent(completed) |
| `tasks/get` | SDK DefaultRequestHandlerV2 | Fetch Task from in-memory TaskStore |
| `tasks/cancel` | OldmanAgentExecutor.cancel | Cancel underlying asyncio task; emit TaskStatusUpdateEvent(canceled) |
| `tasks/resubscribe` | SDK DefaultRequestHandlerV2 | Re-attach SSE to existing Task (in-memory only for v2.0) |

## Discovery

```
GET https://oldman-agent.example/.well-known/agent-card.json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "name": "oldman_agent",
  "url": "https://oldman-agent.example",  ← A2A messaging endpoint (= base URL)
  "capabilities": {"streaming": true, "pushNotifications": false, ...},
  "skills": [
    {"id": "publish_event", "tags": ["publish"], "description": "...metadata.oldman.intent=publish..."},
    {"id": "narrative_query", "tags": ["query","narrative"], "description": "...metadata.oldman.intent=query..."}
  ],
  "x-oldman": {"persona": "꼰대 정보통", "citation_required": true, ...}
}
```

Stock SDK client:
```python
from a2a.client import A2ACardResolver, create_client
import httpx

async with httpx.AsyncClient() as h:
    resolver = A2ACardResolver(h, base_url="https://oldman-agent.example")
    card = await resolver.get_agent_card()
    # → GET https://oldman-agent.example/.well-known/agent-card.json
client = await create_client(card)
# now client can send message/send to card.url
```

## Intent dispatch (the semantic glue)

Default A2A `message/send` doesn't carry "what operation" — the SDK leaves it to the agent. We use `metadata.oldman.intent`:

```python
intent = message.metadata.get("oldman.intent") if message.metadata else None
if intent == "publish":
    data = message.parts[0].root.data  # DataPart contents
    result = run_publish(data)  # M1 logic
    emit_task(state="completed", result_message=ack_message(result))
elif intent == "query":
    question = get_message_text(message)  # SDK helper
    filters = extract_data_part(message)
    task = emit_task(state="submitted")
    emit_status(task.id, state="working")
    narrative = await render_narrative(question, filters)
    emit_artifact(task.id, narrative)
    emit_status(task.id, state="completed")
else:
    # Heuristic default: text content + no intent → assume query
    if has_text(message) and not has_data(message):
        # treat as query with no filters
    else:
        emit_status(state="failed", reason="missing oldman.intent metadata")
```

Skill descriptions in AgentCard document this contract so other agents know what metadata to send.

## Module boundaries (post-v2)

```
app/
  a2a/                             ← NEW (v2)
    executor.py                       OldmanAgentExecutor
    intents.py                        intent constants + dispatch helpers
    task_emitter.py                   helpers to enqueue Task/Status/Artifact events
    routes.py                         create_jsonrpc_routes wiring + .well-known card
    deprecated_routes.py              v1 /publish + /query → executor adapters
  api/
    publish.py                       (deprecated wrapper kept for v1 scripts)
    query.py                         (deprecated wrapper kept for v1 scripts)
    agent_card.py                    /agent-card alias (deprecated path; .well-known is primary)
    schemas.py                       (unchanged)
  reflection/                       (unchanged — M2)
  narrative/                        (unchanged — M3/M4)
  llm/                              (unchanged — v1.0.1+)
  storage/                          (unchanged — M1)
  state/                            (unchanged — M1)
  bootstrap.py                     (extended: also wires TaskStore + AgentExecutor)
  main.py                          (extended: mount JSON-RPC routes + .well-known)
```

## DuckDB single-writer compatibility

A2A introduces no concurrent-write requirements beyond what M1 already imposed. Single uvicorn worker remains mandatory. TaskStore is in-memory in v2.0, so no DB pressure from task lifecycle.

## Deployment topology (single-instance)

```
                Internet
                    │ HTTPS
                    ▼
        ┌─────────────────────┐
        │ Fly.io edge (CDN)   │
        │ → routes to nearest │
        │   running machine   │
        └──────────┬──────────┘
                   │
                   ▼
   ┌──────────────────────────────────┐
   │ fly machine (1 instance)         │
   │  ┌─────────────────────────────┐ │
   │  │ uvicorn workers=1           │ │
   │  │   FastAPI                   │ │
   │  │   + JsonRpc routes (SDK)    │ │
   │  │   + OldmanAgentExecutor     │ │
   │  └─────────────────────────────┘ │
   │  Volume mount: /data             │
   │    oldman.duckdb (persisted)     │
   │  ENV: OPENROUTER_API_KEY,        │
   │       OLDMAN_BASE_URL,           │
   │       OPENROUTER_DEFAULT_MODEL   │
   └──────────────────────────────────┘
```

**Scaling beyond 1 instance** is v3 work — requires:
- Postgres TaskStore (sharable)
- DuckDB → Postgres migration for events/reflections
- LLM router connection-pool tuning

## Test layers (v2 additions)

| Layer | What we test | Tool |
|---|---|---|
| Unit | intent dispatcher, task_emitter helpers, AgentExecutor logic | pytest (existing) |
| Integration | OldmanAgentExecutor.execute against MockProvider with full Task lifecycle | pytest + ASGI in-process |
| **A2A Compliance (NEW)** | `a2a.client.create_client()` round-trip against in-process app — proves real SDK client works | pytest + a2a.client |
| EVAL-1/2 | Reflection accuracy + citation grounding | existing |
| E2E (Docker) | Real OpenRouter call via SDK client against containerized app | shell script |
| **Deployment smoke (NEW)** | After Fly deploy, hit `/.well-known/agent-card.json` + run SDK client against `https://oldman-agent.example` | shell script |

## What hasn't changed since v1

- M1 storage layer (DuckDB schema, transaction discipline, dedup)
- M2 reflection scheduler (BackgroundTasks-driven, post-publish)
- M3 narrative renderer (neutral persona, retry loop, validator)
- M4 LLM judge for content-grounded citation
- v1.0.x: persona toggle, smart MockProvider, defensive provider patches

A2A layer **wraps** these — we did not rewrite domain logic.
