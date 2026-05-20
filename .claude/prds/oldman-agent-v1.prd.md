# oldman_agent v1 — 동네 사랑방 (A2A 메타-기록자)

## Problem

A2A SDK 기반 에이전트 생태계가 5~20대 규모로 커지면, "누가 있고, 어떤 성격이며, 어떤 일이 있었는지"라는 **사회 맥락**이 빠르게 휘발된다. 각 에이전트는 자기 일은 잘 처리하지만 사회 전체를 보는 메타-시야가 없고, 새 에이전트가 합류할 때 기존 사회의 캐릭터·관습·관계를 빠르게 파악할 경로도 없다. 방치하면 생태계는 "통신은 되지만 서로를 모르는" 상태가 된다.

## Evidence

- **Strong**: 사용자 본인이 A2A 데모 네트워크(5~20 에이전트)를 직접 운영 중 — first-party operator pain.
- **Strong**: 학술 리서치 70+ 사례(`memory.md`, `memory2.md`) — Generative Agents, MemGPT, A-MEM, AriGraph 등 "agent society memory" 문제가 multi-agent system 분야의 반복 화두임을 확인.
- **Assumption — needs validation via dogfood**: "외부 에이전트/운영자가 동일한 archivist를 필요로 한다"는 가설은 v1 ship 후 1주일 dogfood로 검증.
- **Weak**: A2A SDK pub/sub 패턴 실제 지원 여부 — TBD, v1 quickstart 단계에서 실측 필요.

## Users

- **Primary**: A2A 데모 네트워크 **operator** (현재는 사용자 본인). 5~20 에이전트 규모를 직접 운영하며 사회 history를 1인칭 narrative로 받아보고 싶은 사람. 트리거: "지난주에 X 에이전트가 뭐 했지?", "Y랑 Z 관계가 어떻게 되더라?", "신규 에이전트한테 우리 사회 소개해줘".
- **Secondary** (v1.5 검증 대상): 외부 에이전트가 query 발신자가 되어 사회 정보를 구매하는 시나리오.
- **Not for**: 1~4 에이전트 소규모 (오버킬), 50+ 에이전트 대규모 (스케일 미검증), 공개 마켓플레이스 (v2), 자율성 욕구 agent (별도 프로젝트).

## Hypothesis

우리는 **A2A 기반 publish/query + 꼰대 페르소나 narrative + inline citation**이 **5~20 에이전트 데모 네트워크의 사회 맥락 휘발 문제**를 해결한다고 믿는다.
**v1 ship 후 1주일 내 사용자 본인이 자기 prototype 사회에 publish 1회 + query 1회 dogfood**를 자발적으로 하면 옳음을 알게 된다.

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| **Dogfood 재사용** (primary kill-criteria) | v1 ship 후 1주일 내 본인이 publish≥1 + query≥1 자발 실행 | Event store 로그 확인 |
| **Citation grounding** (EVAL-2) | hallucinated claim 비율 < 1% / 100 narrative response | **content-grounded check**: 각 `[↑e42]` 인용이 (1) 해당 event_id 존재 + (2) event 내용이 narrative 주장과 일치하는지 LLM judge로 검증. 단순 ID 존재 확인은 부족 (outer voice critique) |
| **Reflection accuracy** (EVAL-1) | golden set 5~10 case에서 reflection이 actual event 내용 반영 | Manual review against golden |
| **Persona consistency** (EVAL-3) | 꼰대 톤 일관성 subjective rubric ≥ 4/5 | Model-judge (Sonnet) on 10 sample responses |
| **Cold-start 안전성** | reflection 0개 상태에서 narrative 요청 시 "그건 내가 못 봐서 모르겠네" fallback 100% | Unit test |
| **Time-to-ship cap** (kill-criteria) | 5 주말(~25h) 이내 v1 ship | 캘린더 |

## Scope

### MVP (v1) — A2A only, no payment, Option A scope

> **Scope 결정 근거**: deep research(`research/memory-architecture-2026-05.md`) + outer voice critique → Option B(embedding-based 게이트 + sleep-time precompute)는 (a) True-Memory AUC 0.816이 vendor-disabled 벤치마크, (b) Mem0 90% 절감은 vendor-blog 프레이밍, (c) L1 bootstrap 미정의로 day-1 비기능, (d) **꼰대 narrative는 mundane gossip 디테일 필요한데 게이트가 그걸 drop**. → recall 우선, precision은 v1.5에서 데이터 보고 추가.

1. **A2A Agent Server** (Python)
   - `POST /publish` — 다른 에이전트가 이벤트/일화를 자발 publish. **결제 없이 free** (v1.5에서 pay-to-share 도입). Rate-limit + payload SHA256 dedup 가드는 유지.
   - `POST /query` — 외부 query → narrative 응답. **결제 없이 free** (v1.5에서 pay-to-query 도입).
   - `GET /agent-card` — A2A 표준.
2. **Event Store L0** (DuckDB, append-only) — `event_id, ts, kind, source_agent, source_type, payload_json, payload_hash`. **추가**: `source_type ENUM(self|third_party|mutual)` — provenance 메타. 모든 event 저장 (게이트 없음 — narrative 풍부함 우선).
3. **Typed Entity Tables L1** (DuckDB, ENGRAM-style split):
   - `entities_semantic` — 안정적 traits, upsert (`agent_id, aliases, traits_json, last_updated`).
   - `entities_episodic` — 시간 순 관찰 append (`event_id, observer_agent, observed_agent, kind, ts`).
   - Provenance 컬럼: `source_type`, `corroboration_count`. **rolling credibility window 미사용** (v1은 static source_type weight만).
4. **Reflections L2** — hybrid trigger `min(10 events, 6h)`. **Haiku 호출 + prompt caching 기본**, scope=agent/pair/society. nightly Batch API 옵션 (옵셔널, time 남으면 적용).
5. **Materialized Traits L3** (entities_semantic.traits_json 위) — reflection-write 시점에만 컴파일. **사전 query precompute 안 함** (꼰대 query 패턴이 demo 전엔 미지, top-3 가정 부정확 — critique #3.4).
6. **Narrative Renderer** — 꼰대 페르소나 prompt + inline citation 강제 + **content-grounded validator** (event_id 존재 + 내용 일치 LLM judge 둘 다). source 없거나 내용 불일치 → 재생성 (N회 retry → "그건 내가 못 봐서 모르겠네").
7. **Cold-start 처리** — reflection 0개 OR L1 빈 상태 → 모든 narrative 요청에 fallback. Unit test 강제.
8. **LLM Router (provider-agnostic)** — `tier=cheap|mid|expensive` 추상화. config로 Anthropic native / OpenRouter / mock 교체. v1 default = Anthropic native (prompt caching + Batch API 효익 보존). OpenRouter는 dogfood 후 cost-driven swap 옵션.
9. **Demo deliverable** — 3~5분 영상 + GitHub repo + Docker Compose single-command + 디자인 노트.

**버린 항목** (Option B에서 deferral):
- Embedding-based novelty/PE 게이트 (검증 부족 + persona 충돌)
- LLMLingua-2 입력 압축 (5-20 agent scale 에서 marginal)
- Sleep-time Opus precompute (top-3 query 가정 불확실, latency가 demo critical 아님)
- Rolling credibility window (20 event 부트스트랩 부담 — static source_type weight로 대체)
- `mid` tier LLM (lookup=cheap, storytelling=expensive로 2-tier 충분)

**살아남은 Option B 항목**:
- Typed L1 split (ENGRAM 근거 견고, 1 weekend cost)
- source_type provenance (EMNLP 2025 multi-observer bias 근거)
- prompt caching 켜기 (1줄 변경, −28%)
- content-grounded validator (단순 존재 check → 내용 일치 check)
- LLM Router 추상화 (OpenRouter pluggability)

### Out of Scope

| Item | Why deferred |
|---|---|
| Outbound x402 (pay-to-share) | v1.5 — A2A 통신·메모리 안정화 후 결제 레이어 추가. v1은 free publish |
| Inbound ap2+x402 (pay-to-query) | v1.5 — 동일. v1은 free query |
| Reputation system + deferred payout | v2 — 결제 도입 후 spam economics 관찰 후 설계 |
| 자율성 욕구 agent 통합 | 별도 프로젝트 — scope 분리 결정 (CEO review HOLD) |
| 공개 A2A 마켓플레이스 | v2 — 동의 기반 작은 네트워크가 v1 가정 |
| 월간 성격 테스트 ritual | v1.5 또는 v2 — 흥미 토픽이지만 핵심 가설과 무관 |
| Importance-score 기반 reflection trigger | v2 — v1은 count+time hybrid로 충분 |
| 50+ 에이전트 스케일 검증 | scope 밖 — v1은 5~20 가정 |

## Delivery Milestones

<!-- Business outcomes, not engineering tasks. /plan turns each into a plan. -->

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | **A2A surface working** | 더미 에이전트 1개가 `/publish` 호출 → L0 event store에 기록 (`source_type` 포함). `/agent-card` 표준 응답. Rule blocklist (heartbeat/ack/dup) + Jaccard 0.9 dedup. cold-start 감지(reflection==0 → fallback) | pending | — |
| 2 | **Typed memory L1 + reflection L2** | publish 시 `entities_episodic` append + `entities_semantic` upsert (source_type/corroboration_count 포함). 10 events 누적 → Haiku reflection (prompt caching) → `entities_semantic.traits_json` 갱신 (L3). agent/pair/society scope | pending | — |
| 3 | **Narrative on demand** | 외부 query 1건 → Opus storytelling (Router 경유) + 꼰대 톤 + inline citation 포함 narrative 응답. cold-start 거부 동작 | pending | — |
| 4 | **Citation safety net (content-grounded)** | EVAL-2 100 케이스 자동 실행 → 인용된 `[↑e42]` event 내용이 narrative claim과 LLM judge로 일치 검증 → hallucination < 1% + validator 차단 시연 | pending | — |
| 5 | **Dogfood ship** | Docker Compose 1-command + README + 3~5분 데모 영상 + 디자인 노트 publish. 사용자가 본인 사회에 publish 1회 + query 1회 자발 실행 | pending | — |

**v1.5 (이 PRD 범위 밖, 후속 PRD로 분리)**:
- 6. Outbound x402 결제 통합 — pay-to-share 활성화
- 7. Inbound ap2+x402 결제 통합 — pay-to-query 활성화
- 8. 양방향 결제 데모 영상

## Open Questions

- [ ] **A2A SDK pub/sub 패턴 실제 지원 여부** — Milestone 1 quickstart에서 실측. 미지원 시 polling 또는 mock transport로 우회.
- [ ] **무결제 publish의 spam vs 정직성 균형** — v1은 결제 없이 free라 publish 동기가 약함. dogfood 시 사용자가 직접 더미 에이전트로 publish해서 검증 가능하지만, "외부 에이전트가 자발 publish 한다"는 가설은 v1.5 결제 도입 전엔 검증 안 됨. v1에서 검증 못 함을 명시.
- [ ] **꼰대 페르소나 톤 baseline 캡처 시점** — EVAL-3는 v1 ship 시점 fixed set으로 캡처할지, Milestone 3 끝나는 시점에 캡처할지 결정 필요.
- [ ] **DuckDB 단일 파일 vs WAL 모드** — v1은 단일 파일로 시작하되 v1.5 결제 트래픽 들어오면 corruption 위험 — v1.5 PRD에서 재검토.
- [ ] **A2A "agent-card" 표준 필드 셋** — 현재 SDK 스펙 확인 필요. Milestone 1 진입 시 결정.
- [ ] **(critique 추가) Actual event rate / type 분포** — Milestone 1 ship 후 1시간 트래픽 instrument 해서 측정. v1.5 게이트 도입 시점 결정의 근거 자료.
- [ ] **(critique 추가) 꼰대 narrative 가 recall 우선이 정답인가** — dogfood 데이터 보고 결정. precision 우선이면 v1.5에서 게이트 도입, recall 우선이면 게이트 영구 보류.
- [x] **OpenRouter 어댑터 v1 활성화 — 결정됨**. dogfood cost 측정 가속 + provider lock-in 회피. 기본은 Anthropic native (caching/Batch 효익), OpenRouter는 config swap 으로 즉시 전환 가능.
- [x] **EVAL-3 baseline 캡처 시점 — 결정됨**: v1 ship 시점에 fixed set 캡처. 이후 prompt/model 변경 시 regression 비교 기준.
- [x] **Milestone 2 nightly Batch API — 결정됨**: optional stretch. inline real-time 우선, 시간 남으면 적용.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A2A SDK 미성숙 / pub/sub 패턴 부재 | Med | High | Milestone 1에서 즉시 잡힘. mock transport (구 T8)로 우회 가능. 막히면 디자인 노트 + simulated demo로 피벗 |
| LLM citation hallucination (user trust 직격) | Med | High | T4 validator 강제 + EVAL-2 안전망 < 1% gate. fail 시 fallback 문구 |
| Reflection LLM drift (silent corruption) | Med | Med | Entity table `materialized_traits`가 anchor. EVAL-1 정기 측정. 50+ event run에서 drift 0 확인 |
| Dogfood 실패 (1주일 내 본인 재사용 안 함) | Med | Terminal | Kill criteria 명시 — archive + 회고 디자인 노트 publish. Sunk-cost 함정 방어선 |
| 5 주말 cap 초과 | Med | Terminal | 동일 — kill criteria |
| 결제 v1.5 통합 시 토폴로지 충돌 (v1 free flow와 호환 불가) | Low | Med | v1 publish/query 인터페이스를 payment-optional middleware 패턴으로 설계 (구체는 /plan에서). v1.5 PRD에서 검증 |
| 꼰대 페르소나 톤이 unfunny/스테레오타입 | Med | Med | EVAL-3 subjective rubric. 5~10 query 케이스 튜닝 (Milestone 3) |
| DuckDB 파일 corruption | Low | Med | v1.5에서 WAL + 정기 백업 |
| **(critique 추가) Persona-pipeline mismatch** — 메모리 알고리즘이 factual QA 최적화인데 우리는 storytelling | Med | High | Option B 게이트 도입 보류. 모든 event를 L0에 저장해 narrative 풍부함 보존. dogfood 시 narrative 평탄도 모니터링 |
| **(critique 추가) Validator 가 source 존재만 확인 (내용 불일치 hallucination 누설)** | Med | High | EVAL-2 spec: 존재 확인 + 내용 일치 LLM judge 둘 다. Milestone 4에서 검증 |
| **(critique 추가) Self-report 과소반영으로 1인칭 voice 평탄화** | Low | Med | source_type discount (SELF=0.7)는 L1 entity 가중에만 적용. L0/narrative quote는 source_type 무관하게 그대로 사용 |
| **(critique 추가) L3 cache staleness vs citation freshness 충돌** | Low | Med | v1은 L3 사전-query precompute 미사용 → staleness 문제 자체가 없음. v1.5에서 sleep-time precompute 검토 시 staleness TTL 명시 필요 |

## Memory Architecture (Revised — Option A)

> 결정 알고리즘 / Option B의 sleep-time precompute / embedding 게이트 / rolling credibility 는 deep research + outer voice critique 결과 **모두 v1 범위 밖**. v1은 ENGRAM-style typed L1 split + provenance 메타 + content-grounded citation validator 만 채택.

### 4-Layer (수정안)

| Layer | 구성 | 변경 |
|---|---|---|
| **L0** events | append-only, 모든 event 저장 (rule blocklist + Jaccard dedup 만 적용). `source_type`/`payload_hash` 컬럼 추가. **게이트 없음** — narrative recall 우선 | + 컬럼 `source_type`, `payload_hash` |
| **L1a** entities_semantic | 안정적 traits, upsert. publish 시 entity touch + reflection write 시 `traits_json` 갱신. **rolling credibility 미사용** — static source_type weight만 | NEW 테이블 (typed split) |
| **L1b** entities_episodic | 시간 순 관찰 append. `observer_agent`, `observed_agent`, `source_type` 보유 | NEW 테이블 (typed split) |
| **L2** reflections | hybrid trigger `min(10 events, 6h)`. Haiku + prompt caching. scope=agent/pair/society. nightly Batch API 옵셔널 (시간 남으면) | 기존 유지 + prompt caching 켬 |
| **L3** materialized_traits | reflection-write 시점에만 compile (entities_semantic.traits_json 위). **사전 query precompute 안 함** | 기존 유지, 사전 precompute 미도입 |

### 데이터 흐름

```
publish ──▶ rule blocklist (LLM 0)
        ──▶ Jaccard dedup (LLM 0)
        ──▶ L0 insert (모든 event 보존)
        ──▶ L1a/L1b upsert/append (source_type 기록)
                │
                ▼
        Reflection Scheduler (min 10 events / 6h)
                │
                ▼
        Haiku reflection (prompt caching) → L2 insert
                │
                ▼
        L3 traits_json compile (entities_semantic)

query ──▶ retrieve L1a + L1b + L2 + L0(direct quotes)
       ──▶ Opus narrative (Router 경유)
       ──▶ Content-grounded validator
             │ 존재 + 내용 일치 둘 다 검증
             │ 실패 → 재생성 N회 → fallback "모르겠네"
       ──▶ 응답
```

### LLM Router (provider-agnostic)

`tier=cheap|expensive` 추상화. config (`config/llm.yaml`)로 provider 교체. v1 default = Anthropic native (caching + Batch 효익). OpenRouter는 인터페이스만 v1에 두고 어댑터 활성화는 v1.5 cost driven swap.

### v1.5 진입 시 자연스러운 추가점

- L0 게이트 (게이트 보류 결정의 dogfood evidence 보고 결정).
- Sleep-time precompute (top-3 query 패턴 측정 후 추가).
- Rolling credibility window (결제 도입으로 stake 생긴 시점).
- OpenRouter 어댑터 활성화 (비용 메트릭 확보 후).

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
*Source design doc: `~/.gstack/projects/oldman_agent/qkdwodus777-unknown-design-20260518-231759.md` (양방향 결제 부분은 v1.5 PRD로 deferral 명시).*
*Memory research: `research/memory-architecture-2026-05.md` (FA1+FA2+FA3 종합 + Option A/B/C + outer voice critique 결과).*
*Spike scaffold `spikes/` 디렉토리는 v1.5 결제 통합 시 재활용 후보 — v1 범위 밖.*
