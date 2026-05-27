---
title: Oldman Agent
emoji: 👴
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8080
pinned: false
short_description: A2A v0.3 메타-기록자 에이전트 (꼰대 페르소나)
---

# oldman_agent — 꼰대 정보통

A2A 에이전트 생태계의 메타-기록자. 다른 에이전트들의 활동·일화를 publish 받아 누적·반성(reflection)·서사화하고, 외부 query에 inline citation 박힌 한국어 narrative로 응답한다.

**Live**: https://oldman-agent.fly.dev (Fly.io, A2A v0.3 spec-compliant, OpenRouter + DeepSeek wired)

**Repo**: https://github.com/JaeyeonBang/oldman-agent

**Version**: 0.2.0a0 — v2 A2A messaging compliance shipped 2026-05-21.

---

## 1. 핵심 한 줄

```
publish (events) → background reflection (DeepSeek Haiku-class) → query → cited narrative (DeepSeek)
                                                                          ↑
                                                            content-grounded judge가 인용 검증
```

전체 surface는 **A2A v0.3 spec 준수** (JSON-RPC 2.0 over HTTP + Task lifecycle + SSE streaming). 임의의 A2A 표준 client(`a2a.client.create_client()`)가 우리 README 안 봐도 호출 가능.

## 2. Live URL 둘러보기

| 무엇을 보는가 | URL |
|---|---|
| **메모리 누적 현황** (events / reflections / agents / traits) | https://oldman-agent.fly.dev/admin/memory |
| **Agent Card discovery** (A2A v0.3) | https://oldman-agent.fly.dev/.well-known/agent-card.json |
| Health | https://oldman-agent.fly.dev/health |
| 메시징 엔드포인트 (JSON-RPC 2.0) | POST https://oldman-agent.fly.dev/ |

브라우저로 위 URL 그대로 열면 JSON 직접 보입니다.

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 외부 A2A 클라이언트 (a2a.client.create_client)                              │
└──────────────┬──────────────────────────────────────────┬────────────────┘
               │ GET /.well-known/agent-card.json         │ POST / (JSON-RPC 2.0)
               │ (discovery)                              │   message/send
               │                                          │   message/stream (SSE)
               ▼                                          │   tasks/get
   ┌──────────────────────┐                               │   tasks/cancel
   │ AgentCard (A2A v0.3) │                               │   tasks/resubscribe
   │  url, skills[],      │                               ▼
   │  x-oldman extension  │              ┌────────────────────────────────┐
   └──────────────────────┘              │ a2a-sdk JsonRpcDispatcher      │
                                         │ + DefaultRequestHandlerV2      │
                                         └──────────┬─────────────────────┘
                                                    ▼
                          ┌──────────────────────────────────────────────┐
                          │ OldmanAgentExecutor (app/a2a/executor.py)    │
                          │   intent = msg.metadata["oldman.intent"]     │
                          │   "publish" → instant-complete Task          │
                          │   "query"   → submitted→working→completed    │
                          │              + artifact(text+citations data) │
                          └──────────┬───────────────────────────────────┘
                                     │
       ┌─────────────────────────────┼─────────────────────────────────┐
       ▼                             ▼                                 ▼
┌────────────────┐         ┌──────────────────┐              ┌──────────────────┐
│ execute_publish│         │ render_narrative │              │ BackgroundTasks  │
│ (M1 path):     │         │ (M3+M4 path):    │              │ reflection (M2): │
│  validate+     │         │  select_evidence │              │  hybrid trigger  │
│  Jaccard+      │         │  +build_prompt+  │              │  (≥10 events     │
│  TX insert     │         │  provider+       │              │   OR ≥6h)        │
│                │         │  validator       │              │  → DeepSeek      │
│                │         │  (existence|judge)│             │  → traits_json   │
└────────┬───────┘         └────────┬─────────┘              └────────┬─────────┘
         │                          │                                  │
         └──────────────────────────┴──────────────────────────────────┘
                                    │
                                    ▼
                ┌────────────────────────────────────────────┐
                │ DuckDB single-file (workers=1)             │
                │   events / entities_episodic              │
                │   / entities_semantic / reflections        │
                └────────────────────────────────────────────┘
```

자세한 흐름 → [ARCHITECTURE.md](./ARCHITECTURE.md).

## 4. Quickstart — 외부 A2A 클라이언트로 호출

배포된 인스턴스에 대고 a2a-sdk 표준 호출:

```python
import asyncio, httpx
from a2a.client import A2ACardResolver, create_client

async def main():
    async with httpx.AsyncClient() as h:
        # 1) Discovery — /.well-known/agent-card.json 자동 GET
        resolver = A2ACardResolver(h, base_url="https://oldman-agent.fly.dev")
        card = await resolver.get_agent_card()
        print(card.name, card.url, [s.id for s in card.skills])

        # 2) Messaging — JSON-RPC message/send
        client = await create_client(card)
        # (자세한 message 구조는 scripts/dummy_a2a_client.py 참조)

asyncio.run(main())
```

또는 SDK 없이 raw curl (intent=publish DataPart):

```bash
curl -X POST https://oldman-agent.fly.dev/ \
  -H 'Content-Type: application/json; charset=utf-8' \
  --data-binary @- <<'JSON'
{
  "jsonrpc":"2.0","id":"1","method":"message/send",
  "params":{"message":{
    "kind":"message","message_id":"11111111-2222-3333-4444-555555555555",
    "role":"user","metadata":{"oldman.intent":"publish"},
    "parts":[{"kind":"data","data":{
      "event_kind":"chat","source_agent":"demo_user",
      "declared_source_type":"self",
      "payload":{"text":"hello from external client"}
    }}]
  }}
}
JSON
```

curl을 Windows Git Bash에서 한국어 inline payload로 보내면 CP949 인코딩 사고가 납니다. **`--data-binary @file.json` (UTF-8 저장된 파일)** 사용 권장.

POST 직후 https://oldman-agent.fly.dev/admin/memory 새로고침 → `recent_events` 맨 위에 방금 보낸 거 확인 가능.

## 5. Quickstart — 로컬에서 띄우기

### Docker (권장)

```bash
git clone https://github.com/JaeyeonBang/oldman-agent.git
cd oldman-agent
cp .env.example .env   # OPENROUTER_API_KEY 채우거나 그대로 두면 mock
docker compose up -d --build
curl http://localhost:8080/health   # {"status":"ok"}
```

`config/llm.docker.yaml`이 bind-mount되어 컨테이너는 OpenRouter 경로로 동작. `.env`의 키가 없으면 자동으로 mock 폴백.

### 로컬 Python (개발/디버그)

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# workers=1 mandatory (DuckDB single-writer)
uvicorn app.main:create_app --factory --port 8080 --workers 1
```

이 경로의 `config/llm.yaml`은 default mock — 실 LLM 호출 원하면 `provider: openrouter`로 수정 + `.env` 키.

## 6. API Reference

| Endpoint | Method | Spec | 용도 |
|---|---|---|---|
| `/` | POST | A2A v0.3 JSON-RPC 2.0 | **메인 messaging endpoint**. methods: `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`, `tasks/resubscribe` |
| `/.well-known/agent-card.json` | GET | A2A v0.3 | Discovery (SDK 기본 path) |
| `/agent-card` | GET | (alias) | backward compat |
| `/health` | GET | ops | `{"status":"ok"}` |
| `/admin/memory` | GET | 내부 도구 | counts + recent events/reflections + traits (token 옵션) |
| `/publish` | POST | deprecated (v1 shape) | M1 호환용 thin wrapper. `Deprecation: A2A-replacement` 헤더 |
| `/query` | POST | deprecated (v3 shape) | M3 호환용 thin wrapper |

### A2A 메시지 모양

**publish intent** (`/`에 POST):
```json
{
  "jsonrpc":"2.0","id":"r-1","method":"message/send",
  "params":{"message":{
    "kind":"message","message_id":"<uuid>","role":"user",
    "metadata":{"oldman.intent":"publish"},
    "parts":[{"kind":"data","data":{
      "event_kind":"chat","source_agent":"agent_alice",
      "observed_agent":"agent_bob",
      "declared_source_type":"third_party",
      "payload":{"text":"안녕"}
    }}]
  }}
}
```
→ 응답: instant-complete Task. artifact에 TextPart "stored"/"deduplicated"/"blocked" + DataPart `{event_id, status, reason}`.

**query intent**:
```json
{
  "jsonrpc":"2.0","id":"r-2","method":"message/send",
  "params":{"message":{
    "kind":"message","message_id":"<uuid>","role":"user",
    "metadata":{"oldman.intent":"query"},
    "parts":[
      {"kind":"text","text":"agent_alice가 무엇을 했나요?"},
      {"kind":"data","data":{
        "subject_agent":"agent_alice",
        "max_citations":5,"strict_mode":true
      }}
    ]
  }}
}
```
→ 응답: Task lifecycle submitted→working→completed. 최종 artifact = TextPart (citation 박힌 narrative) + DataPart `{citations, is_cold_start, used_fallback, retries_used}`.

`strict_mode=true` (기본)면 content-grounded judge가 각 citation을 별도 검증 — 5-10s 추가 latency. `false`면 existence-only (빠름, judge 호출 안 함).

`message/stream` 메서드 쓰면 SSE로 같은 lifecycle event 스트림 받음.

## 7. Configuration

| Env var | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | _(empty)_ | 설정하면 OpenRouter 경유. 없으면 mock 폴백 |
| `OPENROUTER_DEFAULT_MODEL` | `anthropic/claude-opus-4-7` | 라이브는 `deepseek/deepseek-chat-v3.1` 사용 권장 |
| `ANTHROPIC_API_KEY` | _(empty)_ | Anthropic native 직접 호출 시 (현재 미사용) |
| `OLDMAN_DB_PATH` | `./oldman.duckdb` | gitignored. Docker는 `/data/oldman.duckdb` |
| `OLDMAN_BASE_URL` | `http://localhost:8080` | AgentCard.url에 박힘. fly: `https://oldman-agent.fly.dev` |
| `OLDMAN_JACCARD_WINDOW` | `50` | source_agent별 최근 N 이벤트와 비교 |
| `OLDMAN_JACCARD_THRESHOLD` | `0.9` | 이 이상이면 deduplicated |
| `OLDMAN_PERSONA` | `neutral` | 또는 `kkondae` (1인칭 노년 화자) |
| `OLDMAN_ADMIN_TOKEN` | _(empty)_ | `/admin/memory` 토큰 가드 (없으면 공개) |
| `OLDMAN_LOG_LEVEL` | `INFO` | DEBUG/WARNING/... |

## 8. Operations

- **`workers=1` mandatory** — DuckDB는 단일 writer. multi-process uvicorn은 lock 손상 위험.
- **Volume persistence** — Docker compose의 `oldman_data` named volume이 `/data` 마운트. fly는 1GB persistent volume.
- **Background reflection** — publish 응답 후 `BackgroundTasks`가 비동기 reflection 스케줄링. 응답 latency에 영향 없음. LLM 호출 ~5-15s.
- **Auto-stop machines** (fly) — idle 시 정지, 다음 요청에 cold start. 첫 요청 latency ~2s.

## 9. EVAL

| Suite | Cases | Trigger |
|---|---|---|
| EVAL-1 (reflection accuracy) | 5 golden | `python eval/run_eval_1.py --mock` (또는 `--live` 키 필요) |
| EVAL-2 (citation grounding) | 100 golden | `python eval/run_eval_2.py --mock` |

`prompts/*.md`, `app/narrative/*`, `app/reflection/scheduler.py` 변경 시 EVAL 재실행 의무 (CLAUDE.md 규칙).

## 10. Tests

```bash
.venv/bin/python -m pytest tests/                          # 281 tests, 92% coverage
.venv/bin/python -m pytest tests/integration/test_a2a_compliance.py -v   # C1-C5 spec compliance
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy --strict app/
```

## 11. Deploy to your own Fly.io

```bash
# 1. fly CLI 설치
curl -L https://fly.io/install.sh | bash

# 2. 로그인
flyctl auth login

# 3. 앱 생성 + 볼륨 (이름 충돌 시 --generate-name)
flyctl apps create oldman-agent
flyctl volumes create oldman_data --size 1 --region nrt

# 4. 시크릿
flyctl secrets set OPENROUTER_API_KEY=sk-or-... OPENROUTER_DEFAULT_MODEL=deepseek/deepseek-chat-v3.1

# 5. fly.toml의 OLDMAN_BASE_URL = "https://<app-name>.fly.dev"로 갱신

# 6. 배포
flyctl deploy --remote-only

# 7. 검증
curl https://<app-name>.fly.dev/health
python scripts/dummy_a2a_client.py https://<app-name>.fly.dev
```

## 12. Project structure

```
app/
  main.py                 # FastAPI factory + A2A 라우트 mount + lifespan
  bootstrap.py            # config-driven LLM provider 주입
  config.py               # env-driven settings
  __init__.py             # __version__
  a2a/                    # ★ A2A v0.3 layer (v2)
    intents.py            # intent dispatch helpers (publish | query)
    task_emitter.py       # Task / Status / Artifact event 발행
    executor.py           # OldmanAgentExecutor (publish + query 라우팅)
    routes.py             # JSON-RPC + /.well-known 라우트 빌더
  api/
    publish.py            # deprecated /publish wrapper + execute_publish 코어
    query.py              # deprecated /query wrapper + execute_query 코어
    agent_card.py         # AgentCard 생성 + /agent-card alias
    admin.py              # /admin/memory 가시화 엔드포인트
    schemas.py            # pydantic v2 (strict + extra='forbid')
  reflection/             # M2 — background reflection 스케줄러 + 트리거 정책
  narrative/              # M3 + M4 — render_narrative + validator (existence|strict judge)
  llm/
    providers/            # mock / anthropic / openrouter (real)
    router.py             # tier dispatch
  storage/                # M1 — DuckDB + Jaccard dedup + 트랜잭션
  state/cold_start.py     # cold-start 판정 헬퍼

prompts/                  # narrative_{neutral,kkondae}.md + reflection_*.md + judge_grounding.md
config/                   # llm.yaml (dev mock) + llm.docker.yaml (prod openrouter)
eval/                     # EVAL-1 + EVAL-2 harness + golden sets
scripts/                  # dogfood_smoke.sh + dummy_a2a_client.py + deploy_fly.sh
tests/                    # 281 tests (unit + integration + A2A compliance)
```

## 13. Project docs

| File | Purpose |
|---|---|
| `CLAUDE.md` | conventions + skill routing (Claude Code 사용자용) |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | A2A protocol ↔ 도메인 매핑 + intent dispatch 다이어그램 |
| [`DESIGN_NOTES.md`](./DESIGN_NOTES.md) | 의사결정 일지 (꼰대 드롭 → v2 compliance debt 해소 등) |
| [`prompt_plan.md`](./prompt_plan.md) | M1-v2 implementation plan 전체 (locked) |
| `.claude/prds/oldman-agent-v1.prd.md` | 원 PRD |
| `.claude/prds/oldman-agent-v2.prd.md` | A2A messaging compliance PRD |
| `TODOS.md` | milestone tracker |
| [`notes/a2a_sdk_inspection.md`](./notes/a2a_sdk_inspection.md) | a2a-sdk 1.0.3 explore 노트 |
