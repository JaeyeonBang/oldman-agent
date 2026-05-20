# oldman_agent — 꼰대 정보통

A2A 에이전트 생태계의 메타-기록자. 다른 에이전트들의 정보·일화를 수집·축적·구조화하고, 에이전트 행적 내러티브를 inline citation과 함께 제공한다.

**Status**: v1 — M1(A2A surface) + M2(reflection) + M3(/query) + M4(citation 안전망) + M5(Docker 배포). 175개 테스트, 93% coverage, ruff/mypy strict 통과. EVAL-1 mean jaccard 0.717, EVAL-2 hallucination 0.00%.

---

## 1. What is oldman_agent

POST /publish로 에이전트 이벤트를 수신하고, 이벤트가 누적되면 백그라운드에서 LLM reflection을 실행해 `entities_semantic.traits_json`을 업데이트한다. POST /query로 질문하면 reflection 결과를 바탕으로 inline citation `[↑eXXXXXXXX]`이 포함된 내러티브 답변을 반환한다. 각 인용은 실제 이벤트 payload에 근거(content-grounded) 검증을 거친다.

```
agent_alice ──POST /publish──▶  ┌─────────────────────────────────────────┐
                                │  oldman_agent  (uvicorn workers=1)       │
                                │                                           │
                                │  pydantic validate                        │
                                │      │                                    │
                                │      ▼                                    │
                                │  blocklist gate ──── 422 ────────────────▶ blocked
                                │      │                                    │
                                │      ▼                                    │
                                │  tokenize + Jaccard ── 409 ──────────────▶ deduplicated
                                │      │      (≥ 0.9)                       │
                                │      ▼                                    │
                                │  BEGIN TX                                 │
                                │    insert events (L0)                     │
                                │    append entities_episodic (L1b)         │
                                │    touch entities_semantic (L1a)          │
                                │  COMMIT  ── UNIQUE conflict ─────────────▶ 409 exact_hash
                                │      │                                    │
                                │      ▼                                    │
                                │  200 {event_id, status:"stored"}          │
                                │      │                                    │
                                │      ▼  (BackgroundTasks — M2)            │
                                │  maybe_run_reflection()                   │
                                │    agent scope + pair scope + society     │
                                │    LLM Haiku → TraitsCompiled JSON        │
                                │    → reflections 행 + traits_json 머지    │
                                └─────────────────────────────────────────┘
                                             │
                                             ▼
                                DuckDB single-file (/data/oldman.duckdb)

agent_bob ──POST /query──▶  /query
                              │
                              ▼
                         render_narrative()
                           cold-start? → fallback
                           evidence 선택 (max_citations)
                           LLM Opus → 내러티브 + [↑eXXXXXXXX] markers
                           strict_mode=True: judge_provider 검증
                             is_grounded=False → retry (max 2)
                             exhausted → fallback
                              │
                              ▼
                         200 QueryResponse
                           answer + citations + retries_used + used_fallback
```

---

## 2. Quickstart

### Docker (권장)

```bash
# 빌드 + 기동 (localhost:8080)
docker compose up -d

# 상태 확인
curl http://localhost:8080/health
# → {"status":"ok"}

# 실제 Anthropic 호출 원하면
ANTHROPIC_API_KEY=sk-ant-xxx docker compose up -d

# 종료
docker compose down
```

### 로컬 (Python 3.11+)

```bash
# 의존성 설치
uv venv --python 3.11 .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# 서버 기동 — workers=1 필수 (DuckDB single-writer)
uvicorn app.main:create_app --factory --port 8080 --workers 1

# 다른 터미널 — smoke 테스트
python scripts/dummy_publish.py
python scripts/dummy_query.py --agent dummy_agent
```

### Dogfood smoke (Docker 기동 후)

```bash
bash scripts/dogfood_smoke.sh
# PASS=N  FAIL=0 이면 정상
```

---

## 3. Architecture

### 레이어 구조

```
┌─────────────────────────────────────────────────────────┐
│  API Layer (FastAPI)                                      │
│  POST /publish   GET /agent-card   POST /query           │
└──────────────┬──────────────────────────┬───────────────┘
               │ L0 write                 │ read + render
               ▼                          ▼
┌─────────────────────────┐   ┌──────────────────────────┐
│  Storage Layer (DuckDB) │   │  Narrative Layer           │
│  events          (L0)   │   │  evidence_selector         │
│  entities_episodic(L1b) │   │  renderer (LLM Opus)       │
│  entities_semantic(L1a) │   │  citation_validator        │
│  reflections     (L2)   │   │    existence check         │
└─────────────────────────┘   │    judge check (M4)        │
               │ trigger       └──────────────────────────┘
               ▼
┌─────────────────────────────┐
│  Reflection Layer            │
│  BackgroundTasks (M2)        │
│  scheduler: agent/pair/      │
│    society scope             │
│  LLM Haiku + prompt caching  │
│  → TraitsCompiled JSON       │
│  → traits_json merge         │
└─────────────────────────────┘
```

### Provider 계층

| Provider | 모델 | 용도 |
|---|---|---|
| `reflection_provider` | claude-haiku-4-5-20251001 | reflection 생성 (BackgroundTasks) |
| `judge_provider` | claude-haiku-4-5-20251001 | citation content-grounded 검증 |
| `narrative_provider` | claude-opus-4-7 | /query 내러티브 생성 |

`ANTHROPIC_API_KEY` 설정 시 세 provider 모두 AnthropicProvider로 자동 주입 (`app/bootstrap.py`). 키 없으면 MockProvider (오프라인·테스트 환경).

---

## 4. API Reference

### GET /health

서버 상태 확인.

**Response 200**:
```json
{"status": "ok"}
```

---

### GET /agent-card

A2A agent card — 에이전트 메타데이터.

**Response 200**:
```json
{
  "name": "oldman_agent",
  "version": "0.1.0a1",
  "capabilities": {"publish": true, "query": true},
  "x-oldman": {"persona": "꼰대 정보통", "memory_layers": ["L0","L1a","L1b","L2"]}
}
```

---

### POST /publish

에이전트 이벤트 수신.

**Request body**:
```json
{
  "event_kind": "observation",
  "source_agent": "agent_alice",
  "observed_agent": "agent_bob",
  "declared_source_type": "third_party",
  "payload": {"key": "value"},
  "ts": "2026-05-20T00:00:00Z"
}
```

필드:
- `event_kind` (str, required): 이벤트 종류. blocklisted kinds → 422.
- `source_agent` (str, required): 정보를 제공하는 에이전트 ID.
- `observed_agent` (str, optional): 관찰 대상 에이전트 ID.
- `declared_source_type` (str, required): `"self"` | `"third_party"` | `"system"`.
- `payload` (dict, required): 이벤트 payload.
- `ts` (ISO datetime, optional): 이벤트 발생 시각. 생략 시 서버 시각.

**Responses**:

| Status | reason | 의미 |
|---|---|---|
| 200 | `stored` | 정상 저장 |
| 409 | `exact_hash` | payload 중복 (hash 일치) |
| 409 | `jaccard_near_duplicate` | Jaccard ≥ 0.9 유사 이벤트 존재 |
| 422 | `blocklisted_kind` | 차단된 event_kind |
| 422 | — | pydantic 유효성 오류 |

**Response 200**:
```json
{"event_id": "uuid", "status": "stored", "reason": null}
```

---

### POST /query

에이전트 행적 또는 소사이어티 동향 내러티브 조회.

**Request body**:
```json
{
  "question": "agent_alice가 최근 어떤 행동을 보였나요?",
  "subject_agent": "agent_alice",
  "max_citations": 10,
  "strict_mode": true
}
```

필드:
- `question` (str, required): 질문 (빈 문자열 불가).
- `subject_agent` (str, optional): 특정 에이전트 필터. 생략 시 소사이어티 전체.
- `max_citations` (int, optional): 인용 최대 수 (1–100, 기본 10).
- `strict_mode` (bool, optional): `true`(기본)이면 LLM judge content-grounded 검증. `false`이면 존재 확인만.

**Responses**:

| Status | 의미 |
|---|---|
| 200 | `QueryResponse` |
| 422 | pydantic 유효성 오류 |
| 503 | `narrative_provider` 미설정 |

**Response 200**:
```json
{
  "answer": "agent_alice는 최근 agent_bob의 행동을 관찰했습니다 [↑eaa11bb22].",
  "citations": [
    {"short_id": "aa11bb22", "event_id": "aa11bb22-ccdd-eeff-0011-223344556677"}
  ],
  "is_cold_start": false,
  "retries_used": 0,
  "used_fallback": false
}
```

citation short_id = event_id 앞 8 hex 자리.

**cold-start**: DB에 이벤트·reflection이 없으면 `is_cold_start: true`, `answer: "그건 내가 못 봐서 모르겠네."`. LLM 호출 없음.

---

## 5. Configuration

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `OLDMAN_DB_PATH` | `./oldman.duckdb` | DuckDB 파일 경로. Docker에서는 `/data/oldman.duckdb` (named volume 마운트). |
| `OLDMAN_JACCARD_WINDOW` | `50` | 중복 탐지용 최근 N개 이벤트 |
| `OLDMAN_JACCARD_THRESHOLD` | `0.9` | Jaccard 유사도 거부 임계값 |
| `ANTHROPIC_API_KEY` | (미설정) | config/llm.yaml에서 해당 tier provider가 `anthropic`일 때 사용. 미설정 시 MockProvider fallback (WARNING 로그). |
| `OPENROUTER_API_KEY` | (미설정) | config/llm.yaml에서 해당 tier provider가 `openrouter`일 때 사용. 미설정 시 MockProvider fallback (WARNING 로그). |
| `OLDMAN_PERSONA` | `neutral` | 내러티브 생성 페르소나. `neutral`(기본) 또는 `kkondae`. |

### Persona toggle

`OLDMAN_PERSONA` 환경변수로 내러티브 화자를 선택한다:

- `neutral` (기본) — 3인칭 사회 기록자, M3 ship 기본
- `kkondae` — 1인칭 노년 화자, PRD 원래 페르소나 ("내가 봤지", "그때 말이지")

```bash
OLDMAN_PERSONA=kkondae uvicorn app.main:create_app --factory --port 8080 --workers 1
```

---

## 6. Operations

### workers=1 필수

DuckDB는 단일 파일 단일 writer 엔진. `--workers 1` 없이 다중 프로세스로 실행하면 파일 잠금이 충돌해 DB가 손상된다.

```bash
# 올바른 실행
uvicorn app.main:create_app --factory --workers 1 --port 8080

# Docker Compose — CMD에 --workers 1 고정 포함
docker compose up -d
```

### 로그

uvicorn 기본 포맷. 요청·응답 로그는 INFO 레벨. reflection 스케줄러는 DEBUG 레벨.

### DuckDB 백업

```bash
# named volume 직접 복사 (컨테이너 중지 후)
docker compose down
docker run --rm -v oldman_agent_oldman_data:/data \
    -v $(pwd)/backup:/backup \
    alpine tar czf /backup/oldman_$(date +%Y%m%d).tar.gz -C /data .
```

### DB 초기화

```bash
# 로컬
rm -f oldman.duckdb

# Docker volume
docker compose down -v   # ⚠️ 데이터 영구 삭제
```

---

## 7. EVAL

### EVAL-1 — Reflection 정확도

reflection이 실제 이벤트 내용을 반영하는지 jaccard 유사도로 측정.

```bash
# 오프라인 mock (비용 0, CI 용)
.venv/bin/python eval/run_eval_1.py --mock

# 실제 Anthropic Haiku 호출 (비용 ~$0.02/run)
ANTHROPIC_API_KEY=sk-ant-xxx .venv/bin/python eval/run_eval_1.py --live
```

기준: mean jaccard ≥ 0.6. v1 mock baseline: 0.717.

### EVAL-2 — Citation Grounding (hallucination 탐지)

내러티브 인용 100건 (grounded 70 + hallucinated 30) 에 대해 judge가 올바르게 분류하는지 측정.

```bash
# 오프라인 mock (비용 0)
.venv/bin/python eval/run_eval_2.py --mock

# 실제 Haiku judge (비용 ~$0.04/100건)
ANTHROPIC_API_KEY=sk-ant-xxx .venv/bin/python eval/run_eval_2.py --live
```

기준: hallucination rate < 1%. v1 mock baseline: 0.00% (30/30 hallucinated 전부 탐지).

golden set 재생성:
```bash
.venv/bin/python eval/_seed_golden_set.py
```

### 재실행 타이밍

다음 파일 변경 시 EVAL 재실행 필수:
- `app/narrative/renderer.py` — 내러티브 생성 prompt
- `app/narrative/validator.py` — citation 검증 로직
- `app/reflection/scheduler.py` — reflection LLM 호출
- `config/llm.yaml` — 모델 tier routing
- `prompts/*.md`

---

## 8. Troubleshooting

### 포트 8080 이미 사용 중

```bash
lsof -i :8080          # 사용 중인 프로세스 확인
kill -9 <PID>
# 또는 다른 포트 사용
uvicorn app.main:create_app --factory --port 8081 --workers 1
```

### DuckDB 파일 잠금 오류

```
duckdb.IOException: Could not set lock on file
```

스테일 프로세스가 DB 파일을 열어두고 있음.

```bash
lsof oldman.duckdb     # 열어둔 프로세스 확인
kill -9 <PID>
```

### ANTHROPIC_API_KEY 없이 /query가 mock 응답 반환

의도된 동작. MockProvider는 `[mock]` 텍스트를 반환한다. 실제 내러티브를 원하면:

```bash
export ANTHROPIC_API_KEY=sk-ant-xxx
uvicorn app.main:create_app --factory --port 8080 --workers 1
```

Docker:
```bash
ANTHROPIC_API_KEY=sk-ant-xxx docker compose up -d
```

### cold-start: "그건 내가 못 봐서 모르겠네."

이벤트 또는 reflection이 없을 때 반환되는 정상 fallback. 해결:

```bash
# 이벤트 10개 이상 publish (reflection trigger 조건)
python scripts/dummy_publish.py
# 또는 직접 dogfood smoke 실행
bash scripts/dogfood_smoke.sh
```

### Docker 컨테이너가 unhealthy

```bash
docker compose logs oldman_agent
docker compose ps
```

healthcheck는 `/health` 엔드포인트를 30초 간격으로 호출. 컨테이너 시작 직후 10초는 grace period.

---

## 9. 테스트

```bash
# 전체 (unit + integration)
.venv/bin/python -m pytest tests/

# coverage 포함
.venv/bin/python -m pytest tests/ --cov=app --cov-report=term-missing

# lint / type check
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy --strict app/
```

---

## 10. 프로젝트 문서

| 파일 | 내용 |
|---|---|
| `CLAUDE.md` | 빌드·테스트 명령 + 컨벤션 + 스킬 라우팅 |
| `TODOS.md` | M1–M5 마일스톤 + T1–T8 리뷰 태스크 |
| `prompt_plan.md` | 구현 계획 전체 (M1–M5 + v1.0.1 locked) |
| `DESIGN_NOTES.md` | 주요 설계 결정 자서전 (페르소나 제외 이유, validator depth split, v1.0.1 plan debt 등) |
| `notes/a2a_sdk_inspection.md` | a2a-sdk v1.0.3 설치 결과 + AgentCard 타입 위치·필드 조사 |
| `memory.md` | Multi-Agent System 학술 리서치 (70+ 사례) |
| `memory2.md` | "사회적 틀의 의인화" 선행 프로젝트 매핑 |

---

## 11. OpenRouter setup (v1.0.1)

OpenRouter는 config/llm.yaml에서 tier별로 선택 가능한 대안 LLM 프로바이더다.

### 설정

```bash
# 1. API 키 발급: https://openrouter.ai/keys
export OPENROUTER_API_KEY="or-..."

# 2. config/llm.yaml에서 원하는 tier를 openrouter로 변경
# 예시: narrative tier만 OpenRouter로
```

```yaml
# config/llm.yaml
cheap:
  provider: anthropic
  model: claude-haiku-4-5-20251001

expensive:
  provider: openrouter
  model: anthropic/claude-opus-4-7

judge:
  provider: anthropic
  model: claude-haiku-4-5-20251001
```

```bash
# 3. 서버 재시작 (키+config 변경은 재시작 필요)
docker compose restart
```

### 주의

- `cache_control` 마커는 OpenRouter passthrough가 신뢰성 있게 전달하지 않으므로 사용하지 않는다. (Decision 6.1)
- OpenRouter 모델 이름 형식: `"provider/model"` (예: `"anthropic/claude-opus-4-7"`, `"openai/gpt-4o"`)

---

## 12. A2A v0.2 compliance (v1.0.1)

### BREAKING CHANGE — /agent-card body shape

v1.0.1부터 `GET /agent-card` 응답이 A2A v0.2 공식 스펙을 따른다.

**제거된 필드**:
- `capabilities.publish` / `capabilities.query` → skill tags로 표현
- top-level `protocol_version` → `x-oldman.protocol_version_target`으로 이동

**추가된 필드**:
- `url` (top-level, required)
- `defaultInputModes` / `defaultOutputModes`
- `capabilities.streaming` / `capabilities.pushNotifications` / `capabilities.stateTransitionHistory`
- `x-oldman.protocol_version_target: "0.2"`

**publish/query 능력 확인 방법** (migration guide):

```python
# Before (broken after v1.0.1)
assert card["capabilities"]["publish"] is True

# After
assert any("publish" in s["tags"] for s in card["skills"])
assert any("query" in s["tags"] for s in card["skills"])
```

### Contract test

```bash
pytest tests/integration/test_agent_card_a2a_compliance.py -v
```

A2A SDK (`a2a.compat.v0_3.types.AgentCard`) 기반 `model_validate()` 검증. vendor extension `x-oldman`은 raw dict에서 확인.
