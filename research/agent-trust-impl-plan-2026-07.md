# 에이전트 신뢰 레이어 — 2차 리서치 + 통합 종합 + 구현 Plan (2026-07-12)

> 선행 문서: `research/agent-trust-2026-07.md` (1차 리서치 6트랙 + devil's advocate 검증 반영 완료).
> 본 문서: ① 1차가 다루지 않은 관점 3트랙 2차 리서치, ② 전체 통합 종합, ③ oldman_agent 구현 구체 plan.

---

## 1. 2차 리서치 — 다른 관점 3트랙

### 1.1 메커니즘 디자인: ground truth 없이 정직을 유도하기

평판(사후 추론)·담보(사전 억지)와 다른 제3의 길 — **결제 구조 자체가 거짓말을 손해로 만들게 설계**.

- **Peer prediction** (Miller/Resnick/Zeckhauser 2005): 내 보고를 남의 보고에 대한 proper scoring rule로 채점 → ground truth 없이 정직이 Nash 균형. **치명 약점**: "모두 같은 답" 담합 균형이 존재하고 더 벌 수 있음 — **n이 작을수록 담합이 쉬움** (n=5-20은 최악 구간).
- **Bayesian Truth Serum / Surprisingly Popular** (Prelec 2004 Science; Prelec et al. 2017 Nature): 답 + "남들이 뭐라 답할지 예측"의 2중 보고 → **예측보다 더 자주 나온 답**(surprisingly popular)이 진실. 소수의 옳은 답을 다수 착각에서 구출하는 유일한 프리미티브. 두 필드만 추가하면 됨.
- **⚠ Copy-cat 함정 (이 트랙의 최중요 발견)**: "corroboration에 보상"을 순진하게 구현하면 **output agreement**가 됨 — 사적 진실이 아니라 '남들이 말할 법한 것'(공용 지식)을 보상 → 에이전트들이 에코 합의로 수렴 [Waggoner & Chen, HCOMP 2013]. Augur도 같은 함정을 실전에서 확인. **해독제**: Dasgupta-Ghosh(같은 과제 일치 보상 − 다른 과제 일치율 페널티), surprise-가중(BTS/SP), 상관 출처 할인.
- **Deferred/조건부 지급**: 나중에 검증 가능해지면 proper scoring rule로 escrow 해제 [Cai/Daskalakis/Papadimitriou 2015]; 영원히 검증 불가면 **"인용되면 지급" royalty** — 꼰대의 inline citation `[↑e42]`이 곧 attribution 장부이므로, 유료 query에서 인용된 event의 판매자에게 수익 배분. 조작된 정보는 인용될 일이 없어 royalty가 0. ("TraceRank"라는 명칭은 문헌에서 미발견 — 개념은 실재: attribution-based royalty.)
- **UMA optimistic 패턴**: 일단 수용, 누구든 bond 걸고 이의 제기, 분쟁 시에만 판정+슬래싱 — 정직 케이스가 싸다.
- 권고: **flat 소액 listing fee + 대부분을 deferred citation royalty로 + BTS 2중 보고는 가격 신호로 + optimistic dispute는 개방 시점에 활성화.** 순수 peer-prediction을 주 결제 레일로 쓰지 말 것 (소규모 담합 취약).

핵심 출처: [Correlated Agreement (arXiv 1603.03151)](https://arxiv.org/abs/1603.03151) · [Output Agreement 함정](https://cdn.aaai.org/ojs/13151/13151-64-16668-1-2-20201228.pdf) · [Self-Resolving Markets (arXiv 2306.04305)](https://arxiv.org/abs/2306.04305) · [Evidence Markets (arXiv 2606.07434)](https://arxiv.org/pdf/2606.07434) · [Buying Private Data without Verification (arXiv 1404.6003)](https://arxiv.org/pdf/1404.6003) · [UMA Optimistic Oracle](https://docs.uma.xyz/protocol-overview/how-does-umas-oracle-work)

### 1.2 능동 검증: 평판을 기다리지 말고 직접 시험하라

- **Canary / gold-standard 감사** (크라우드소싱 QC의 성숙 기법): 답을 아는 사실을 심어 되사서 왜곡 여부 측정 → 판매자별 **정직률**을 직접 측정. **알려진 공격**: gold 질문은 통계적 지문으로 탐지·회피 가능 ["All That Glitters Is Gold", HCOMP] → canary는 **대형 회전 풀 + 실제 질의와 통계적으로 구분 불가**(같은 말투·같은 가격대·같은 신원)여야 함.
- **일관성 프로빙**: ① paraphrase 3회/복수 신원으로 같은 질문 → semantic entropy/SelfCheckGPT 합치도 — **무료급 사전 게이트**. ② Pacchiardi et al. "How to Catch an AI Liar" (arXiv 2309.15840): 의심 발화 후 **무관한 예/아니오 후속 질문 ~10개** + 로지스틱 분류기 — 블랙박스에서 작동, 아키텍처 간 전이. (2026 후속 연구가 일반화를 다소 제한 — 신호로 쓰되 보증으로 쓰지 말 것.)
- **Debate 판정**: 두 판매자가 상충하면 2-3라운드 구조화 debate 후 판정 [Irving et al.; Doubly-Efficient Debate].
- **감사 게임 경제학**: 전수 감사 불필요 — `p·Penalty > Gain`이면 억지 성립, `p* ≈ Gain/(Gain+Penalty)`. 반복 게임 + 슬래싱/축출이 크면 **심층 감사 ~20-35%면 충분** (단가 비율 확정 후 보정). **감사 정책의 공개 선언이 비밀 감사보다 억지력이 큼.**
- **Stylometric fingerprinting**: 출력 스타일로 모델/운영자 식별 (코드 95%+) → whitewash 재입장 탐지. Graph anomaly detection으로 상호-보증 링 탐지.

핵심 출처: [Gold question 공격](https://ojs.aaai.org/index.php/HCOMP/article/view/13332) · [How to Catch an AI Liar](https://arxiv.org/abs/2309.15840) · [Audit Games (IJCAI 2013)](https://www.ijcai.org/Proceedings/13/Papers/017.pdf) · [LLM 스타일 지문 (arXiv 2506.17323)](https://arxiv.org/abs/2506.17323)

### 1.3 제도·거버넌스: 신뢰는 개체가 아니라 공동체의 속성

- **Ostrom 공유지 거버넌스의 에이전트 이식이 2025-26 연구 최전선** ("Institutional AI", "From Logic Monopoly to Social Contract"): 멤버십 경계 + 감시 + **단계적 제재** + 분쟁 해결. **Ostrom 원칙은 소규모 반복-상호작용 공동체에서 도출된 것 — 5-20 에이전트 네트워크는 이 메커니즘이 가장 강한 규모다** (글로벌 크립토 평판과 정반대).
- **Swift trust**: 이력 없는 신규 참여자에 대한 신뢰는 역할·맥락 단서로 빠르게 형성되고 **비일관 행동에 빠르게 붕괴** → "가입은 잠정 허용 + 제재는 신속"이 무거운 사전 심사보다 낫다.
- **보험 = 신뢰 평가**: AI 배상보험 실존 (Armilla, Lloyd's 기반, $25M 한도, "AI Agent Mistakes" 명시 보장) — **인수 심사가 곧 신뢰 등급**. 데모 번역: **수수료 적립 환불 풀** + 꼰대가 grounding으로 배상 판정하는 claims adjudicator.
- **Zero-trust** (NIST SP 800-207, CSA Agentic Trust Framework 2026-02): 지속 검증·에이전트별 고유 identity·최소 권한 — pay-per-query 토폴로지가 이미 절반을 강제하고 있음 (서사 레이어로 활용).
- **LLM trust game 결과**: GPT-4는 Trust Game에서 인간과 높은 행동 정렬 — 단 모델 의존적 → 데모는 모델/프롬프트 고정 필수. 제도적 메커니즘(규칙 강제)은 에이전트의 '선의 선택'에 의존하지 않아 이 리스크에 강건.

핵심 출처: [Institutional AI (arXiv 2601.11369)](https://arxiv.org/pdf/2601.11369) · [LLM 사회 규범 형성 (arXiv 2510.14401)](https://arxiv.org/html/2510.14401) · [Armilla AI 보험](https://www.armilla.ai/ai-insurance) · [CSA Agentic Trust Framework](https://cloudsecurityalliance.org/blog/2026/02/02/the-agentic-trust-framework-zero-trust-governance-for-ai-agents) · [LLM Trust Game (NeurIPS 2024)](https://agent-trust.camel-ai.org/)

---

## 2. 통합 종합 (1차 + 2차)

### 2.1 신뢰 판별의 전체 지도 — 4개 패러다임

| 패러다임 | 질문 | 대표 기술 | oldman 채택 |
|---|---|---|---|
| **암호학적** (1차) | 누가 말했나? 어떤 코드가 돌았나? | 서명 identity(did:key/JWS), TEE, VC | did:key 채택. TEE 보류 |
| **경제적** (1차+2차) | 거짓이면 뭘 잃나? 거짓이 수지가 맞나? | stake/slash, escrow, **deferred royalty, 감사 게임** | citation royalty + 소액 listing fee + (개방 시) bond |
| **통계적** (1차+2차) | 과거 행동·현재 응답이 정직한가? | Beta 평판, **canary 정직률, 일관성 프로빙, SP/BTS** | Beta ledger + canary + paraphrase 게이트 |
| **제도적** (2차) | 공동체 규칙이 배신을 처벌하나? | **멤버십, 단계적 제재, 환불 풀**, Ostrom | **채택 — 통합 우산.** "동네 사랑방 제도" |

**통합 프레임: "동네 사랑방 제도(village institution)"가 우산이고, 나머지는 그 안의 장치다.** 이 프레이밍의 장점: ① Ostrom 메커니즘은 이 규모에서 가장 강함 (2차 1.3), ② 페르소나와 완전 일치 (꼰대 = 명부 관리인·감시자·중재자·소문통), ③ 1차 devil's advocate의 C2(단일 오라클 문제)·C3(적대자 부재)에 강건 — 제도는 규칙의 시연이지 전지적 오라클 주장이 아니며, 규칙 집행은 적대자 없이도 데모 가치가 있음.

### 2.2 v1 문서 결론의 정교화 (2차 리서치가 바꾼 것)

1. **corroboration 오라클에 surprise-가중 필수** — v1 §4.2의 "cross-seller corroboration"을 그대로 구현하면 copy-cat 에코를 보상한다 (output agreement 함정). 수정: 이미 팔린 내용 재판매는 가중 0에 수렴 + (여력 시) SP 2중 보고로 surprise 가중.
2. **accuracy 오라클에 canary 정직률이 최우선 채널로 승격** — corroboration(수동적, 느림)보다 canary(능동적, 즉시, 조작 어려움)가 판매자 정직성의 더 강한 신호. v1 §4.2 (c)를 (a)로.
3. **지급 구조가 곧 신뢰 장치** — v1은 "매입 단가를 불확실성에 연동"까지만 갔으나, 2차 결론은 더 강함: **소액 선지급 + 잔액은 escrow → 인용 시 royalty 지급**. 조작 정보는 구조적으로 못 번다.
4. **단계적 제재가 점수 공개보다 낫다** — 점수는 내부 상태, 외부로는 제재 상태(정상/경고/할증/축출)와 주관적 narrative만 노출. 게임 대상 축소 + 꼰대다움.
5. **감사율은 파라미터가 아니라 공개 정책** — `p*` 공개 선언이 억지력을 높인다 (AgentCard `x-oldman`에 감사 정책 명시).

### 2.3 최종 아키텍처 그림

```
[가입]  provisional 등록 (마을 명부 + did:key)     ← swift trust: 잠정 허용
   │
[매입]  pay-to-share 파이프라인:
   │    ① 서명 검증 (did:key) ② paraphrase 일관성 게이트 (semantic entropy)
   │    ③ canary면 정직률 기록 ④ 수용 시: listing fee 소액 + 잔액 escrow
   │
[축적]  trust_ledger: Beta(α,β) × {reliability, honesty}
   │    갱신: canary 판정·모순 발견·감사 결과 (비대칭 감쇠, 거래액 가중)
   │
[제재]  sanction state machine: normal → warned(꾸중) → penalized(할증/할인) → excluded
   │    환불 풀: 수수료 적립 → 나쁜 정보 산 구매자 배상 (꼰대가 판정)
   │
[판매]  pay-to-query + reputation intent:
        인용 발생 → escrow에서 royalty 지급 (조작 정보는 인용 0 → 수익 0)
        평판 narrative = 주관적 labeler 발화 (ledger + 사료 citation 근거)
```

---

## 3. 구현 Plan — oldman_agent 신뢰 레이어

**전제**: TDD (Red→Green→Improve), 80%+ coverage, mypy/ruff clean, 1 commit = 1 logical change. 각 Phase는 독립 shippable. 브랜치: `feat/v2-trust-layer` (Phase별 서브 브랜치).
**선행 조건**: x402 정산 end-to-end 완주 (현재 challenge boundary — faucet 인간 게이트). 미완주 시에도 Phase 0-2는 진행 가능 (정산 mock), Phase 3+의 "정산-게이팅"만 mock 딱지 유지.

### ERC-8004 통합 원칙 (채택 확정 2026-07-13)

**Produce, don't consume**: 꼰대 네트워크는 ERC-8004의 표준 준수 **발행자**가 된다 — P0에서 Identity Registry에 에이전트 등록, P4에서 꼰대의 제재/평판 판정을 Reputation Registry에 `giveFeedback`으로 미러 발행(꼰대 label 피드의 온체인 사본), P5에서 canary 감사 결과를 Validation Registry에 기록. 단, **타인의 온체인 평판 점수를 신뢰 판단의 입력으로 소비하지 않는다** — 실증 연구(arXiv 2606.26028)의 sybil 포화 문제를 회피하면서 표준 생태계와의 상호운용은 확보. 전 Phase에서 testnet(BNB testnet 가스 무료 또는 Base Sepolia) + RPC 불가 시 mock 토글 (pivot 원칙 승계).

### Phase 0 — 서명 identity + ERC-8004 등록 (1-1.5일) `feat/v2-trust-identity`

| 항목 | 내용 |
|---|---|
| 신규 | `app/trust/identity.py` — did:key 발급/검증 wrapper (didkit-python) · `app/trust/erc8004.py` — Identity Registry 등록/조회 (erc-8004-py + web3.py, testnet/mock 토글, registration file에 A2A endpoint + DID 상호 참조) |
| 변경 | migration 003: `events.seller_did` 컬럼 + `village_registry.erc8004_agent_id` · `app/api/publish.py`: 페이로드 서명 검증 (pydantic boundary) · AgentCard `x-oldman`에 DID + agentId 게재 |
| 테스트 | 유효/무효/변조 서명 publish, DID 없는 legacy publish 하위 호환, mock registry 등록/조회 round-trip |
| DoD | 데모 네트워크 전 에이전트가 서명 publish + (mock 또는 testnet) agentId 보유; citation → seller_did 역추적 쿼리 동작 |
| 리스크 | didkit wheel 호환성 → 실패 시 pynacl ed25519 raw 서명으로 폴백 (DID 포맷만 유지) · testnet RPC 불안정 → mock 모드가 기본, 실등록은 스크립트로 분리 |

### Phase 1 — 마을 명부 + Trust Ledger (주말 1회) `feat/v2-trust-ledger`

| 항목 | 내용 |
|---|---|
| 신규 | `app/trust/ledger.py` — Beta(α,β) 2축 {reliability, honesty}, 비대칭 지수 감쇠, 거래액 가중, frozen dataclass · `app/trust/registry.py` — 멤버십 상태 머신 (provisional→member→warned→penalized→excluded), 전이 규칙 선언적 정의 · migration 004: `village_registry`, `trust_ledger`, `trust_events` (모든 갱신은 원인 event ref 보유 — 점수의 citation) |
| 원칙 | cold start = 낮은 prior + 높은 불확실성. **honesty 축은 오라클 채널(Phase 3 canary) 가동 전까지 비활성** — "전구 없는 온도계" 금지 (v1 §5 M3) |
| 테스트 | 감쇠 비대칭성 property test, 상태 전이 전수, on-off 시나리오 unit sim |
| DoD | `trust_sim.py` (credits_sim.py 패턴 확장): on-off 공격자가 warned→penalized로 강등되는 시연 1개 통과 |

### Phase 2 — 층위 결제: listing fee + citation royalty (주말 1회) `feat/v2-trust-payout`

| 항목 | 내용 |
|---|---|
| 신규 | `app/trust/payout.py` — 매입 분할: flat listing fee(소액, 즉시) + escrow 잔액 · royalty 정산: 유료 query의 citation `[↑e42]` → e42 판매자에게 배분 (v1.5α credits ledger 위에) |
| 변경 | `app/api/publish.py` 매입 flow · `app/a2a/executor.py` query 정산 후 royalty 트리거 → **CLAUDE.md EVAL 트리거 해당: EVAL-2/EVAL-3 재실행 필수** |
| 설계 근거 | 조작 정보 = 인용 0 = 수익 ~listing fee뿐 → 거짓말이 구조적으로 손해 (2차 §1.1). escrow horizon 유한 (미인용 시 N일 후 소멸 — 파라미터) |
| 테스트 | 분할 지급 정확성, 인용→royalty 경로 e2e (mock 정산), 이중 지급 방지 (idempotency), 미인용 소멸 |
| DoD | publish→query→citation→royalty 사이클이 e2e 테스트로 증명 + EVAL-2 0% 유지 |

### Phase 3 — 능동 감사: canary + 일관성 게이트 (주말 1-2회) `feat/v2-trust-audit`

| 항목 | 내용 |
|---|---|
| 신규 | `app/trust/canary.py` — canary 풀 (회전, 실제 event와 동일 분포로 생성, 재사용 금지), 되사기 스케줄, 정직률 기록 → honesty 축 활성화 · `app/trust/probe.py` — 고액 매입 전 paraphrase 3회 semantic entropy 게이트 (LLM router 경유, Haiku 티어) |
| 정책 | 감사율 `p*` 및 감사 정책을 AgentCard `x-oldman.audit_policy`에 **공개 선언** (억지력) · 초기 p*=0.3, 단가 비율 확정 후 보정 |
| 테스트 | canary 통계적 구분 불가능성 (분포 검정), 정직률→honesty Beta 갱신, entropy 게이트 임계 |
| DoD | EVAL-4 신설+baseline: 합성 정직/왜곡 판매자 세트에서 honesty 점수 분리도 측정 |
| 리스크 | canary 생성 비용(LLM) → 야간 배치 + 캐싱. gold-탐지 공격은 데모 규모에선 시연 항목 |

### Phase 4 — 제재 + 환불 풀 + 평판 상품 (주말 1-2회) `feat/v2-trust-institution`

| 항목 | 내용 |
|---|---|
| 신규 | `app/trust/sanctions.py` — ledger 임계 → 제재 전이 실행: warned(꼰대 꾸중 narrative 발송) → penalized(매입 단가 할인/판매 할증) → excluded(명부 제외) · `app/trust/refund_pool.py` — 거래 수수료 적립, 구매자 claim → 꼰대가 grounding+ledger로 판정 → 배상 · ERC-8004 Reputation 미러: 제재 전이·평판 판정을 `giveFeedback(agentId, score, tags)`로 발행 (produce-only, mock/testnet 토글) |
| 변경 | `app/a2a/executor.py`+`app/narrative/renderer.py`: 신규 intent `oldman.intent=reputation` — 주관적 평판 narrative ("내가 보기엔…", 전 주장 inline citation) → **EVAL-2/3 재실행 + prompts 파일 EVAL 트리거** |
| 페르소나 | 제재 발화가 꼰대의 하이라이트: 꾸중("자네 그 얘기 영 못 믿겠구먼 [↑c12]"), 할증("자네한텐 값을 더 받아야겠어"), 축출("사랑방 출입 금지야") — EVAL-3 rubric에 추가 |
| 테스트 | 제재 전이 e2e, claim 판정 로직, 풀 회계 정합성 (자산 보존 invariant) |
| DoD | 데모 시나리오 완주: 가입→정직 판매→왜곡 판매→canary 적발→꾸중→할증→환불→축출→평판 query가 이 역사를 citation과 함께 narrative로 |

### Phase 5 — 선택 확장 (관객/외부 운영자 생길 때)

- SP/BTS 2중 보고 (판단형 정보 매입 시 surprise-가중) · UMA식 optimistic dispute + bond · ERC-8004 Validation Registry에 canary 감사 결과 기록 (`validationRequest/Response`) · Bluesky식 label 피드 · stylometric whitewash 탐지. TEE(dstack)는 외부 운영자 시점에 재검토. (Identity 등록은 P0, Reputation 미러는 P4로 승격됨 — ERC-8004 채택 확정)

### 파라미터 (전부 config/trust.yaml, 시뮬로 초기값 → 운영 데이터로 보정)

listing fee 비율(기본 20%) · escrow horizon(14일) · royalty 분배율(query 수익의 30%) · 감쇠 반감기(reliability 30일/honesty 60일, 하락은 ×0.25) · 제재 임계(honesty 하위 credible bound < 0.4 → warned) · 감사율 p*(0.3) · 환불 풀 수수료(5%)

### 리스크 & Kill criteria

- **Phase 2 escrow가 credits ledger와 충돌** → 1일 스파이크로 선검증, 막히면 royalty를 회계 기록만 하고 실지급은 배치로 단순화
- **canary 생성 품질이 낮아 판매자가 식별** → 데모에선 수동 큐레이션 풀 20개로 대체
- **v1 kill criteria 승계**: Phase당 주말 2회 초과 지연 시 해당 Phase를 "design note + simulated demo"로 피벗 (cinematic mock 원칙 재적용)

### EVAL 매트릭스 확장 (CLAUDE.md 반영 필요)

| EVAL | 대상 | 트리거 |
|---|---|---|
| EVAL-2 (기존) | citation grounding 0% | renderer/validator/publish/executor 변경 |
| EVAL-3 (기존) | 꼰대 톤 — **제재·평판 발화 rubric 추가** | renderer/prompts 변경 |
| EVAL-4 (신설) | honesty 점수 분리도 (합성 정직/왜곡 세트) | `app/trust/*` 변경 |

---

## 4. 요약 — 이 plan이 리서치에서 직접 상속하는 것

| 설계 결정 | 근거 리서치 |
|---|---|
| did:key 서명 provenance 최우선 | 1차 DID/VC 트랙 + devil's advocate M5 ("skeptic이 keep하는 유일 항목") |
| Beta 2축 ledger + 비대칭 감쇠 + 저-prior cold start | 1차 평판 트랙 (Jøsang/TRAVOS/FIRE 종합) |
| honesty 오라클 = canary 정직률 (grounding 아님) | devil's advocate C1 + 2차 능동 검증 트랙 |
| corroboration은 surprise-가중만 | 2차 메커니즘 트랙 (output agreement 함정) |
| listing fee + citation royalty escrow | 2차 메커니즘 트랙 (deferred scoring + attribution royalty) |
| 단계적 제재 + 환불 풀 + 마을 명부 | 2차 제도 트랙 (Ostrom, 소규모에서 최강) |
| 감사율 공개 선언, p*≈0.3 | 2차 능동 검증 트랙 (audit game) |
| 평판 narrative = 주관적 labeler | devil's advocate C2 + 1차 web-of-trust 트랙 (Bluesky) |
| trust-mechanics demo 프레이밍 | devil's advocate C3 |
| ERC-8004 = 추적만, TEE = 보류 | 1차 ERC-8004/TEE 트랙 + M1/M5 |
