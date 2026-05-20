# DESIGN_NOTES — oldman_agent v1 설계 결정 자서전

작성: 2026-05-20. 자율 구현 세션 (M1–M5) 종료 시점 기준.

이 문서는 v1 구현 과정에서 내려진 주요 설계 결정들을 결정 순서대로 기록한다.
"왜 그렇게 했는가"를 미래의 자신과 협력자를 위해 남긴다.

---

## 1. 꼰대 페르소나 제외 (M3, 2026-05-20)

### 결정

v1에서 꼰대 페르소나를 구현하지 않는다. `prompts/narrative_neutral.md`는 중립적 3인칭 요약 톤을 사용한다.

### 배경

PRD와 초기 설계에서 "꼰대 정보통 — 1인칭 노년 화자, inline citation 강제"가 핵심 차별점이었다. M3 구현 직전에 사용자가 명시적으로 방향을 전환했다: **"꼰대톤 제외하고 계속 스스로 진행"**.

### 이유 (추정 및 확인된 것)

1. **citation validator 연동 복잡도**: 꼰대 1인칭 화법은 "내가 그 자리에서 봤는디..." 형태의 주관적 서술을 생성한다. 이 서술이 citation으로 뒷받침되어야 하는지, 단순 화법인지를 judge가 구분해야 한다. EVAL-3 (페르소나 일관성) 하니스를 별도로 구축해야 하며, citation grounding과 페르소나 일관성이 충돌하는 케이스가 많다.
2. **스코프 우선순위**: M3–M4 핵심 가치는 "인용의 신뢰성"이다. 페르소나는 표면 계층 — 신뢰성이 먼저다.
3. **복원 비용 낮음**: 페르소나는 system prompt 1개 교체로 복원 가능하다. `prompts/narrative_kkondae.md`를 작성하고 `config/llm.yaml`에서 선택하면 된다.

### 복원 방법 (v1.5)

```bash
# 1. prompts/narrative_kkondae.md 작성 (꼰대 system prompt)
# 2. config/llm.yaml에 narrative_prompt_path 추가
# 3. EVAL-3 하니스 구축 (페르소나 일관성 rubric)
# 4. renderer.py에서 config 분기
```

EVAL-3 없이 페르소나만 바꾸면 citation grounding과 충돌하는 케이스가 늘어난다 — 반드시 함께 구축할 것.

---

## 2. Validator Depth Split: Existence (M3) → Judge (M4)

### 결정

M3에서 citation 검증을 "event_id 존재 확인"으로 먼저 구현하고, M4에서 LLM judge 기반 content-grounded 검증으로 확장했다.

### M3 existence-only 선택 이유

- /query 엔드포인트를 먼저 동작시키는 것이 목표였다. citation validator가 없으면 LLM이 없는 event_id를 만들어내는 hallucination을 막을 수 없다.
- LLM judge를 M3에 함께 넣으면 EVAL-2 하니스 없이 judge 품질을 검증할 수 없다. "judge가 잘못 판단해도 알 수 없는" 상태로 ship하는 것은 더 위험하다.
- existence check는 결정론적 — 테스트가 쉽고 회귀가 없다.

### M4 judge 확장 이유

- existence check는 "event_id가 있다"는 것만 확인한다. LLM이 올바른 event_id를 인용하되 그 이벤트와 무관한 주장을 하는 케이스를 잡지 못한다.
- 100-case golden set (hallucinated_invented_agent, hallucinated_timestamp_swap, hallucinated_role_swap, hallucinated_fabricated_field)으로 judge를 검증할 수 있게 된 시점에 확장했다.
- EVAL-2 mock baseline 0.00% — judge 로직이 올바름을 확인하고 M4를 닫았다.

### 비용 트레이드오프

- existence-only: 추가 LLM 호출 없음 (비용 $0)
- judge: citation당 Haiku 호출 1회 (~$0.0002/citation). 10개 citation = ~$0.002/query. 허용 가능.
- `strict_mode=false`로 opt-out 가능 — dogfood smoke가 이 경로를 사용한다.

---

## 3. BackgroundTasks로 Reflection 비동기화 (M2)

### 결정

reflection은 `/publish` 응답 후 FastAPI `BackgroundTasks`로 실행한다. 동기 실행하지 않는다.

### 선택 이유

1. **응답 지연 제거**: reflection은 LLM 호출 1–3회 포함 → 수백 ms~수 초. publish를 기다리는 caller에게 이 지연을 노출하는 것은 잘못된 API 계약이다.
2. **트리거 조건**: `events ≥ 10` 또는 `age ≥ 6h AND events ≥ 1`. 대부분의 publish는 reflection을 트리거하지 않는다 — 동기화해도 비용 없지만, 트리거될 때 caller가 타임아웃을 겪는다.
3. **단순성**: Celery/ARQ 같은 태스크 큐를 도입하면 Redis dependency + 워커 프로세스가 추가된다. v1 스코프에서는 DuckDB도 단일 파일이고 workers=1이므로 BackgroundTasks로 충분하다.

### 한계 (알고 선택한 것)

- 컨테이너 재시작 시 in-flight reflection이 유실된다. 다음 트리거 조건 충족 시 재시도된다 — v1 데모 스케일에서 허용 가능.
- uvicorn 재시작 중 BackgroundTask 완료 보장 없음. 프로덕션 스케일에서는 Celery/RQ + Redis 필요.

---

## 4. Anthropic-first + OpenRouter 보류

### 결정

LLM provider를 Anthropic SDK 직접 구현으로 시작하고, OpenRouter를 `openrouter.py` 스텁(미완성)으로 보류했다.

### 이유

1. **속도**: Anthropic API는 직접 구현이 httpx 한 파일이다. OpenRouter는 API 키 + 라우팅 로직 + 에러 포맷 차이를 추가로 처리해야 한다.
2. **prompt caching**: Anthropic은 `cache_control: {type: ephemeral}` 마커로 system prompt 캐싱이 가능하다. reflection system prompt는 반복 호출 — 캐싱으로 비용 40–90% 절감. OpenRouter 경유 시 캐싱 적용 여부가 불확실하다.
3. **비용 메트릭 없음**: OpenRouter 스왑의 가치는 실제 호출 비용 데이터가 있어야 판단 가능하다. dogfood 1주일 후 메트릭 보고 결정.

### v1.5 진입 조건

- dogfood 1주일 데이터: reflection 평균 비용 > $0.01/event → OpenRouter 비용 비교
- 또는: 다른 LLM provider(Gemini, Llama)가 필요한 기능이 생길 때

---

## 5. T1–T4 Engineering Review 수정 사항

M1 구현 후 engineering review에서 발견된 4개 핵심 이슈. 모두 M1 단계에서 수정했다.

### T1 — `events.payload_hash` UNIQUE 제약

**발견**: payload_hash 중복 삽입이 레이스 컨디션에서 두 번 성공할 수 있었다.
**수정**: `001_init.sql`에 `UNIQUE` 제약 추가. `publish.py`에서 `duckdb.ConstraintException` 캐치 → `exact_hash` 응답.
**교훈**: 해시 dedup은 애플리케이션 레벨만으로 레이스-세이프하지 않다. DB 제약이 최후 방어선.

### T2 — 명시적 BEGIN/COMMIT/ROLLBACK 트랜잭션

**발견**: L0 insert + L1b append + L1a touch가 각자 auto-commit으로 실행되어 L0 성공 후 L1 실패 시 inconsistency 발생 가능.
**수정**: 세 헬퍼 모두 cursor를 받도록 변경. publish 핸들러에서 `BEGIN` → 세 헬퍼 → `COMMIT`, 예외 시 `ROLLBACK`.
**교훈**: 헬퍼에 connection을 넘기면 각자 트랜잭션을 만든다. cursor 주입 패턴이 명시적 트랜잭션 경계를 강제한다.

### T3 — tokenize 엣지 케이스

**발견**: 빈 payload, 한글만, 숫자만, boolean, null 값에서 tokenize가 빈 집합을 반환하거나 Jaccard가 0 나누기를 일으킬 수 있었다.
**수정**: tokenize에 엣지 케이스 처리 추가. Jaccard 분모 0 → 0.0 반환 (중복 아님).
**교훈**: NLP 토크나이저는 비ASCII, 비공백 언어(한국어)에서 예상대로 동작하지 않는다. 별도 테스트 케이스 필수.

### T4 — 동시 same-hash 삽입 회귀 테스트

**발견**: UNIQUE 제약이 있어도 `threading`으로 동시 삽입을 테스트하지 않으면 행동을 보장할 수 없다.
**수정**: `test_concurrent_same_hash_returns_one_success_one_conflict` 추가. Thread 2개 동시 삽입 → 정확히 1 success + 1 conflict.
**교훈**: 레이스 컨디션은 "있을 것 같다"가 아니라 "실제로 테스트해야" 보인다.

---

## 6. Kill Criteria (CEO Review에서 도입)

CEO 리뷰에서 명시적 종료 조건을 설정했다. "언제 그만할지"를 미리 정하는 것이 feature creep 방지의 핵심.

**Kill Criteria 1 — 시간 cap**: v1을 5 주말 안에 ship하지 못하면 → 정리. v1은 2026-05-19~20 이틀 만에 M1–M5 완료. Kill criteria 충족.

**Kill Criteria 2 — Dogfood 실패**: v1 ship 후 1주일 내 자기 자신이 재사용하지 않으면 → 정리. 1주일 후 판단 예정.

Kill criteria가 있으면 "조금 더 하면"의 유혹을 명시적 판단으로 대체할 수 있다.

---

## 7. v1에서 의도적으로 제외한 것들

v1을 제시간에 ship하기 위해 명시적으로 제외한 기능들. "하지 않기로 결정"한 것이지 "잊은 것"이 아니다.

### x402/ap2 결제 (v1.5)

양방향 결제 토폴로지 (pay-to-share + pay-to-query)는 PRD의 핵심 차별점. 그러나:
- x402 프로토콜 스파이크가 1일 이상 막히면 "Design note + simulated demo" 피벗 조건이 있었다.
- Spike A (outbound x402)와 Spike B (inbound ap2)를 실제로 진행하기 전에 HTTP-only 구현으로 v1 core를 먼저 ship하는 것이 더 가치 있다고 판단.
- v1.5에서 `spikes/outbound_x402.py` 스캐폴드를 재활용.

### Demo 영상

자동화 불가 — 인간 녹화 필요. M5 스코프에서 제외. `scripts/dogfood_smoke.sh`로 기술적 검증은 가능하다.

### EVAL-3 페르소나 일관성

꼰대 페르소나가 제외되었으므로 EVAL-3도 불필요해졌다. 페르소나 복원 시 함께 구축.

### OpenRouter 실제 구현

`app/llm/providers/openrouter.py`는 스텁 상태. dogfood 비용 데이터 확인 후 결정.

### Embeddings + 벡터 검색

evidence selector가 현재 SQL 기반 (agent_id 필터 + 최근 N개). embedding 기반 의미 검색은 v2에서 검토. DuckDB VSS extension이 옵션.

### Streaming SSE

/query 응답이 현재 단발성 JSON. 긴 내러티브에서 TTFB가 크다. v1.5에서 SSE 추가 고려.

---

## 8. 아키텍처 결정: DuckDB 선택

### 선택 이유

1. **단일 파일**: 의존성 없음. `./oldman.duckdb` 하나로 전체 상태 관리.
2. **분석 쿼리 친화적**: reflection scheduler가 최근 N개 이벤트를 집계하는 쿼리를 실행한다. DuckDB의 columnar 엔진이 이 패턴에 적합.
3. **Python 네이티브**: `pip install duckdb` 하나. SQLAlchemy 없이 직접 사용.

### 한계 (알고 선택한 것)

- **단일 writer**: workers=1 필수. 다중 프로세스 uvicorn 불가. v1 데모 스케일에서 허용 가능.
- **네트워크 공유 불가**: NFS/EFS 마운트에서 파일 잠금이 깨진다. 분산 배포가 필요하면 PostgreSQL로 전환.
- **WAL 모드 없음**: v1에서 정기 백업을 수동으로 해야 한다. v1.5에서 DuckDB WAL 모드 + 정기 백업 검토.

---

## 9. bootstrap.py — 제5마일스톤 추가

M5 Docker 배포를 위해 `app/bootstrap.py`를 추가했다. `configure_providers(app)`이 `create_app()` 내부에서 호출되어 `ANTHROPIC_API_KEY` 환경변수 기반으로 provider를 자동 주입한다.

### 이전 방식의 문제

M1–M4에서 provider는 테스트 픽스처가 `app.state.x = ...`로 직접 주입했다. 실제 서버 기동 시 provider를 주입하는 표준 방법이 없었다 — Docker 컨테이너에서 `/query`가 항상 503을 반환했다.

### bootstrap 설계

- `ANTHROPIC_API_KEY` 있음 → AnthropicProvider 3개 (reflection Haiku, judge Haiku, narrative Opus)
- `ANTHROPIC_API_KEY` 없음 → MockProvider 3개 (오프라인·테스트 환경)
- `create_app()` 호출 후 `app.state.x = custom`으로 덮어쓰기 가능 (기존 테스트 픽스처 패턴 유지)
- idempotent: 두 번 호출해도 에러 없음

### 기존 테스트 픽스처 영향

bootstrap이 MockProvider를 주입하게 되면서 "provider 미설정" 시나리오를 테스트하는 픽스처 3개를 수정했다:
- `app_no_provider`: `del app.state.narrative_provider`
- `seeded_app_no_judge`: `del app.state.judge_provider` + `del app.state.reflection_provider`
- `seeded_app` / `m3_smoke_client`: MockProvider judge 대신 grounded judge 주입

모두 surgical edit — 테스트 의도는 변경하지 않았다.

---

## 10. Lessons Learned & v1.5 Backlog Seeds

### 잘 된 것

- **TDD strict**: 모든 기능을 Red→Green→Improve 순서로 구현. 회귀가 거의 없었다.
- **EVAL 먼저**: EVAL-2 golden set을 M4 구현 전에 설계했다. judge 로직을 "통과시키는 방향"이 아니라 "측정하는 방향"으로 작성.
- **단계적 validator depth**: existence → judge 순서가 올바른 순서였다. judge 없이 존재 검증만으로도 LLM이 없는 event_id를 만들어내는 hallucination은 잡힌다.
- **미리 정한 Kill criteria**: "5 주말" cap이 feature creep을 막았다.

### 개선할 것

- **MockProvider의 judge 영향**: bootstrap이 MockProvider judge를 기본 주입하면서 기존 픽스처 3개를 수정해야 했다. 테스트가 "provider 없음" 상태를 전제할 때는 픽스처 설계 시 명시적으로 del을 포함해야 한다.
- **reflection 유실**: BackgroundTasks 기반 reflection은 재시작 시 유실된다. 데모 스케일에서는 허용했지만, 프로덕션에서는 태스크 큐 필요.
- **DuckDB 단일 writer**: 가장 큰 운영 제약. workers=1을 README, Dockerfile CMD, docker-compose 모두에 명시했지만 실수할 여지가 있다. 진입점에서 workers 수를 런타임에 확인하는 가드 추가 고려.

### v1.5 우선순위

1. x402 outbound (pay-to-share) — 핵심 차별점
2. ap2 inbound (pay-to-query) — 수익 모델
3. 꼰대 페르소나 + EVAL-3 — 원래 차별점 복원
4. Streaming SSE — UX
5. OpenRouter cost-driven swap — 비용 최적화 (데이터 확보 후)

---

## Plan debt resolution (v1.0.1) — 2026-05-20

### 배경

M1-M5 ship 후 두 가지 PRD-locked promise가 미이행 상태였다:
1. `openrouter.py`가 `NotImplementedError("wired in M2")`를 올리는 stub 그대로였다.
2. `/agent-card`가 A2A v0.2 spec과 다른 hand-rolled 형태였다 (capabilities.publish/query, top-level protocol_version — 스펙에 없는 필드).

User direction 2026-05-20: "둘다 추가해. plan에 반영하고 이를 기반으로 sonnet agents로 tdd진행".

### 결정 사항

**D6.1 — OpenRouterProvider real impl**: `httpx.AsyncBaseTransport` 주입 패턴을 AnthropicProvider에서 그대로 미러. endpoint `https://openrouter.ai/api/v1/chat/completions`, OpenAI-compatible messages 형식. `cache_control` 마커 제외 — OpenRouter passthrough가 Anthropic 캐싱을 신뢰성 있게 전달하지 않으므로.

**D6.2 — Config-driven bootstrap**: `app/bootstrap.py` 재작성. `config/llm.yaml`이 tier별 provider + model을 결정. env var는 credential 전용. 키 부재 시 MockProvider fallback + WARNING 로그. `judge` tier 추가 (기존 cheap/expensive 외).

**D6.3 — LLMConfigError 이전**: `app/llm/providers/anthropic.py` → `app/llm/base.py`. 두 provider가 공유. anthropic.py에서 backward-compat re-export 유지.

**D6.4 — a2a-sdk 선택**: `a2a-sdk==1.0.3` 설치 성공. `a2a.types.AgentCard`는 protobuf(url 필드 없음) — 부적합. `a2a.compat.v0_3.types.AgentCard`가 pydantic v2 + A2A v0.2 public spec과 일치 → 이것을 contract test에 사용.

**D6.5 — /agent-card A2A v0.2 migration (breaking change)**:
- 제거: `capabilities.publish`, `capabilities.query`, top-level `protocol_version`
- 추가: `url`(top-level), `defaultInputModes`, `defaultOutputModes`, `capabilities.streaming/pushNotifications/stateTransitionHistory`
- publish/query 능력은 skill tags로 표현: `publish_event` → tags=["publish"], `narrative_query` → tags=["query","narrative"]
- `protocol_version`은 `x-oldman.protocol_version_target`으로 이동
- vendor extension `x-oldman` 유지 + `protocol_version_target: "0.2"` 추가

### 영향 범위

- `test_smoke.py::test_smoke_full_publish_cycle` — `capabilities.publish` 단언 제거, skill tags 검사로 교체
- `test_llm_router.py` — OpenRouter stub 테스트 2개 교체 (real provider + key 필요)
- `test_schemas.py::test_agent_card_alias_serialization` — v0.2 형태로 업데이트
- 총 3개 M1-M5 테스트 surgical update (예상 범위 내)

### 결과

- 201/201 tests GREEN, coverage ≥80%, ruff/mypy --strict clean
- Contract test: `/agent-card` response → `a2a.compat.v0_3.types.AgentCard.model_validate()` 성공
- OpenRouter: 7개 MockTransport 기반 unit test, 실제 API 호출 없음

---

## 8. v1.0.2 Tier 1 polish — 세 가지가 함께 묶인 이유 (2026-05-20)

### 결정

Smart MockProvider (A) + CI workflow (B) + 꼰대 페르소나 토글 (C)을 하나의 Tier 1 번들로 묶어 구현한다.

### 왜 세 가지가 함께인가

세 항목은 표면적으로 무관해 보이지만 공통 원인을 공유한다: **"no-key 개발 환경에서 전체 파이프라인이 작동하지 않는다"**.

- **A (Smart MockProvider)**: `MockProvider`가 `"[mock]"` 리터럴만 반환해 reflection 스케줄러가 JSON 파싱 실패 → `reflections` 테이블이 비어 있음 → `/query`가 항상 cold-start 반환. `dogfood_smoke.sh`가 이를 확인함. 수정: `mode` 필드로 tier별 유효 JSON 반환.
- **B (CI)**: mock-only 파이프라인이 완성됐으므로 이제 CI에서 `ANTHROPIC_API_KEY` 없이 전체 게이트를 실행할 수 있다. 키가 없어도 CI가 돌아가야 기여자가 생긴다.
- **C (페르소나 토글)**: M3 설계 결정("꼰대 제외, 1-line swap 주석")이 실제로는 코드 경로가 없었다. A가 완성돼 mock narrative가 유효해지면 kkondae prompt를 테스트할 수 있게 된다 — A 없이 C를 검증하면 LLM 호출이 필요했을 것이다.

순서 의존성: A → B (CI가 no-key로 돌아가려면 A 필요) → C (persona smoke가 A의 mock narrative 위에서 작동).

### Smart MockProvider mode 설계

`@dataclass(frozen=True)` 에 `mode: str = "bare"` 필드 추가. `__post_init__`에서 유효성 검사. `complete()`는 mode별 분기:

| mode | 반환 |
|---|---|
| `bare` | `"[mock]"` (M1 기존 계약 유지) |
| `reflection` | `TraitsCompiled` 유효 JSON |
| `narrative` | `req.prompt`에서 `[↑e<8hex>]` 최대 3개 추출 → 인용 포함 텍스트 |
| `judge` | `JudgeVerdict` 유효 JSON (`is_grounded: true`) |

Bootstrap은 tier 이름 → mode 매핑을 `_build_provider` 내부에서 처리. 외부 인터페이스 무변경.

### 페르소나 토글 설계

`load_narrative_prompt(persona: str | None = None)`: `None` → `OLDMAN_PERSONA` env → `"neutral"` 폴백 체인. `_PERSONA_FILE_MAP` dict로 파일 경로 선언적 관리. 알 수 없는 persona → `ValueError` (즉시 실패, 묵묵한 폴백 금지).

기존 `load_narrative_prompt()` 호출자(인자 없음) → 계속 neutral 반환. 하위 호환.

### 결과

- 228+ tests GREEN (201 → +27), coverage ≥93%
- `test_full_pipeline_with_smart_mock_no_keys` — 10 publish → reflection landing → /query citations, no API keys
- `.github/workflows/ci.yml` + `.pre-commit-config.yaml` 유효 YAML 확인
- `OLDMAN_PERSONA=kkondae` env로 페르소나 즉시 전환 가능

---

## v2 — closing the A2A compliance debt (2026-05-21)

### 1. v1 misleading deferral 인정

v1은 자신을 "A2A 에이전트"로 광고하면서 실제로는:
- `a2a-sdk`를 AgentCard **타입 검증 1개 기능만** 사용
- `POST /publish` + `POST /query`는 **custom HTTP API** — JSON-RPC 2.0 envelope 없음,
  Task lifecycle 없음, `message/send` 메서드 없음, SSE 없음
- → 표준 A2A 클라이언트 (`a2a.client.create_client()`)는 우리 카드만 읽을 수 있고
  publish/query 호출 불가

v1 PRD는 이를 "semantic mismatch (Task lifecycle vs publish webhook)"로 명명하고
deferral 처리했다. **이는 false advertising이었다.**

### 2. semantic-mismatch 해소 — intent dispatch

v2는 표준 A2A `message/send` 위에 **intent-based dispatch**를 얹는다:

- `message.metadata["oldman.intent"] = "publish" | "query"` 로 동작 분기
- `publish`: instant-complete Task (`submitted → completed` + ack artifact)
- `query`: 정상 lifecycle (`submitted → working → completed` + narrative artifact)
- 미설정 시: TextPart only → heuristic = query / 그 외 → failed (helpful error)

AgentCard skill description에 이 contract를 명시.

### 3. v2.0 ships / v2.1 leaves

**v2.0 ships**:
- `OldmanAgentExecutor` (a2a.server.agent_execution.AgentExecutor 서브클래스)
- JSON-RPC routes: `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`,
  `tasks/resubscribe` (모두 `enable_v0_3_compat=True` SDK 활용)
- `GET /.well-known/agent-card.json` (SDK-standard discovery path)
- `AgentCard.url` = `OLDMAN_BASE_URL` env (배포 시 `https://<app>.fly.dev`)
- `capabilities.streaming = True`
- C1-C5 compliance suite green (`tests/integration/test_a2a_compliance.py`)
- 기존 `/publish` `/query` 는 deprecated wrapper로 유지 (Deprecation 헤더 부착)
- 도메인 로직 분리: `execute_publish()` / `execute_query()` — wrapper와 executor가 공유

**v2.1 defers**:
- `tasks/pushNotificationConfig/*` (webhook) — 작업이 < 30초면 불필요
- 영속 TaskStore (DuckDB-backed) — 5-20 agent demo scale에서는 in-memory 충분
- 재시작 후 `tasks/resubscribe` — 영속 TaskStore에 종속

### 4. 영수증

- 250 → 278 tests GREEN (+28, 92% coverage)
- ruff + mypy --strict clean
- EVAL-1 mock 0.717 / EVAL-2 mock 0 hallucination
- C1-C5 all PASS
- 배포는 `fly.toml` + `scripts/deploy_fly.sh` + `scripts/post_deploy_verify.sh` 준비됨
