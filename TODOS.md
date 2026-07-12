# TODOS — oldman_agent

## Current state (2026-05-20 — v1.0.2)

- PRD: `.claude/prds/oldman-agent-v1.prd.md` (Option A memory architecture)
- Implementation plan (M1): `prompt_plan.md` (engineering-reviewed, T1-T8 applied)
- Research: `research/memory-architecture-2026-05.md` (deep research + outer voice critique)

## v1 Milestones (PRD)

- [x] **M1 — A2A surface working**: publish/agent-card + L0 + rule blocklist + Jaccard dedup + cold-start helper. *Shipped 2026-05-19, 54/54 tests, 96% coverage.*
- [x] **M2 — Typed memory L1 + reflection L2**: entities_semantic + entities_episodic + Haiku reflection (prompt caching) + traits_json compile. *Shipped 2026-05-20, 105/105 tests, EVAL-1 mean jaccard 0.717.*
- [x] **M3 — Narrative on demand**: POST /query + evidence selector + citation validator + retry loop + neutral-tone summarizer (꼰대 페르소나 제외). *Shipped 2026-05-20, 157/157 tests, ≥80% coverage, ruff/mypy clean.*
- [x] **M4 — Citation safety net**: content-grounded validator (LLM judge) + EVAL-2 100-case harness, hallucination rate 0.00% (mock mode, threshold < 1%). *Shipped 2026-05-20, 187/187 tests, ruff/mypy clean.*
- [~] **M5 — Dogfood ship**: Docker Compose single-command + README polish + DESIGN_NOTES.md + bootstrap provider wiring. *Partial — 2026-05-20. Core v1 ship complete. Demo 영상은 인간 녹화 필요 → 사용자에게 위임.*
- [x] **v1.0.1 — Plan debt resolution**: OpenRouter real provider + config-driven bootstrap + a2a-sdk adoption + /agent-card A2A v0.2 compliance. *Shipped 2026-05-20, 201/201 tests, ruff/mypy clean.*
- [x] **v1.0.2 — Tier 1 polish**: Smart MockProvider (mode-aware) + CI workflow + pre-commit config + 꼰대 페르소나 토글 (OLDMAN_PERSONA). *Shipped 2026-05-20, 228+ tests, ≥93% coverage.*

## M5 entry checklist (when starting M5)

- [x] `Dockerfile` + `docker-compose.yml` (uvicorn --workers 1, DuckDB mount) — done 2026-05-20
- [x] `app/bootstrap.py` — provider auto-wiring (mock default, Anthropic if key set) — done 2026-05-20
- [x] `scripts/dogfood_smoke.sh` — /health + 10×publish + /query + assertions — done 2026-05-20
- [x] README consolidation (quickstart, arch, API ref, config, ops, EVAL, troubleshooting) — done 2026-05-20
- [x] `DESIGN_NOTES.md` — 설계 결정 자서전 (페르소나 제외, validator split, etc.) — done 2026-05-20
- [ ] Demo video (인간 참여 필요 — 자동화 불가) → **사용자에게 위임**
- [x] **EVAL-1 live baseline capture** — *DONE 2026-05-31 via OpenRouter. mean jaccard **0.593** (4/5 PASS, case_04 WARN at 0.200). 결과: `eval/baselines/v2.5_live_baseline.md`*
- [x] **EVAL-2 live baseline capture** — *DONE 2026-05-31 via OpenRouter. **0/100 = 0.00% hallucination rate**, 30/30 TP, 0/70 FP. PASS. 결과: `eval/baselines/v2.5_live_baseline.md`*

## M1 Engineering Review tasks (apply during Phase 1.x)

- [x] **T1 (P1)** Add UNIQUE constraint on `events.payload_hash` + IntegrityError handling → race-safe dedup — *DONE (migration 001 line 16 + publish.py:192-197)*
- [x] **T2 (P1)** Wrap `publish()` handler in explicit BEGIN/COMMIT/ROLLBACK transaction → L0/L1 consistency — *DONE (publish.py:157-202)*
- [x] **T3 (P1)** Specify + test `tokenize` edge cases (empty / unicode-Korean / numeric / boolean / null) — *DONE (tests/unit/test_dedup.py:25-46)*
- [x] **T4 (P1)** Regression test: concurrent same-hash insert returns exactly 1 success + 1 conflict — *DONE 2026-05-31 (tests/unit/test_adversarial_v102.py::test_concurrent_same_hash_publish_yields_one_success_one_dedup_error)*
- [x] **T5 (P2)** README: `uvicorn --workers 1` mandatory + DuckDB single-writer rationale — *DONE 2026-05-31 (README §8 Operations: lock 충돌·race-safety backstop·DuckDB→Postgres 마이그레이션 조건)*
- [x] **T6 (P2)** ASCII diagrams in `app/api/publish.py` + `app/storage/dedup.py` top-of-file — *DONE 2026-05-31 (v2.5 race-safety 흐름 + error mapping + 두 dedup layer 명시)*
- [x] **T7 (P2)** Sync TODOS.md with new PRD milestones — DONE
- [x] **T8 (P3)** A2A SDK pub/sub spike deferred to M2 entry checklist — *DONE (M2 spike verdict in spikes/a2a_pubsub_probe.md)*

## M2 entry checklist (when starting M2)

- [x] A2A SDK pub/sub spike (60 min hard timebox, exit-condition list ready) — verdict: HTTP-only continuation, see `spikes/a2a_pubsub_probe.md`
- [x] Decide: activate Anthropic provider first (M2) — DONE, AnthropicProvider real impl with prompt caching
- [x] LLM Router stubs → real implementations (Anthropic done, OpenRouter stays stub for M3)
- [x] Reflection scheduler implementation — DONE (Phase 2.4)
- [ ] Nightly Batch API optional — DEFERRED to M3 per plan §9

## Pivot Triggers (from CEO review)

- Spike or critical M1 blocker eats >1 day → consider "Design note + simulated demo" pivot

## Kill Criteria (from CEO review)

1. **시간 cap**: v1을 **5 주말 안에 ship 못하면** (pivot 포함) → 정리
2. **Dogfood 실패**: v1 ship 후 **1 주일 내 자기 자신이 재사용 안 하면** → 정리

둘 중 하나라도 hit → 명시적 archive + 디자인 노트 publish (실패 회고 포함)

## v1.5 (deferred — separate PRD)

- [~] **Spike A — Outbound x402 (pay-to-share)** — *VERIFIED to challenge boundary 2026-05-31. Server-side x402 v2 stack works (HTTP 402 + decoded challenge JSON proves SDK + middleware + USDC Base Sepolia config). Final mile (signed payment + facilitator settlement) blocked only by faucet human captcha. Outcome: `spikes/spike_a_outcome.md`. Not a pivot — concrete evidence of design hypothesis.*
- [~] **Spike B — Inbound ap2+x402 (pay-to-query)** — *VERIFIED to challenge boundary 2026-05-31. `POST /invoice` 200 + valid ap2 IntentMandate + W3C PaymentRequest carrying x402-exact settlement metadata. `POST /query` 402 (x402 middleware gating). 양방향 결제 토폴로지 가설 SDK+protocol 레벨에서 양쪽 다 확정. Final mile (buyer wallet) 동일 human-gate. Outcome: `spikes/spike_b_outcome.md`. Scaffold: `spikes/inbound_ap2.py`.*
- [ ] L0 gate (Haiku triage 등) — dogfood 데이터 보고 도입 여부 결정
- [ ] Sleep-time precompute — top-3 query pattern 측정 후
- [ ] Rolling credibility window — 결제 stake 생긴 후
- [ ] OpenRouter 실제 비용 driven swap (메트릭 확보 후)

## v2 — Trust Layer "동네 사랑방 제도" (방향 확정 2026-07-13)

> 설계 근거: `research/agent-trust-2026-07.md` (1차 6트랙 + devil's advocate) + `research/agent-trust-impl-plan-2026-07.md` (2차 3트랙 + 구현 plan).
> 프레이밍: trust-mechanics demo. 꼰대 = 주관적 평판 labeler. 스택: x402 = 정산 레일(전 Phase), AP2 = 위임/mandate(v1.5 wiring 유지), ERC-8004 = **채택 (2026-07-13)** — P0 Identity 등록 + P4 Reputation 미러 발행 + P5 Validation 기록. 원칙: produce-only (타인 온체인 평판을 신뢰 입력으로 소비하지 않음 — sybil 실증 회피).
> 구 "Reputation system + deferred payout (TraceRank-style)" 항목을 아래 Phase들이 대체 ("TraceRank" 명칭은 문헌 미발견 → citation royalty).

- [x] **P0 — did:key 서명 identity + ERC-8004 Identity 등록** — *Shipped 2026-07-13 (`feat/v2-trust-identity`). pynacl 직접 구현 채택(didkit 불요 — P0에 VC 불필요), Mock Identity Registry + agent_identities. 306+24 tests.*
- [x] **P1 — 마을 명부 + Trust Ledger** — *Shipped 2026-07-13. Beta 2축 + 비대칭 감쇠(fall ×4) + 저-prior cold start Beta(1,3). trust_sim.py 3가설 확증 (on-off 라운드11 강등→excluded).*
- [x] **P2 — listing fee + citation royalty escrow** — *Shipped 2026-07-13. royalty_enabled 토글(기본 off). migration 005+006. EVAL-1/2 mock 재실행 PASS (0 FP).*
- [x] **P3 — canary 감사 + paraphrase 일관성 게이트** — *Shipped 2026-07-13. 1회용 canary + jaccard 판정 → honesty 축 활성화. EVAL-4 신설 + baseline (분리도 0.769 PASS). audit_policy 카드 공개(OLDMAN_AUDIT_RATE).*
- [~] **P4 — 단계적 제재 + reputation intent + ERC-8004 미러** — *Core shipped 2026-07-13: 가격 정책+꾸중 템플릿 v0+giveFeedback 미러+`oldman.intent=reputation`(주관적 labeler, template v0). **잔여**: ① refund pool ② LLM renderer 통합(꼰대 페르소나 프롬프트 — prompts 변경이므로 EVAL-2/3 재실행+rubric 확장 필요, 사용자 검토 권장) ③ 데모 시나리오 완주 스크립트*
- [ ] **P5 — 개방 시 확장** (외부 운영자/관객 생길 때): SP/BTS 2중 보고, UMA식 optimistic dispute, ERC-8004 Validation Registry 기록, Bluesky label 피드, TEE(dstack) 재검토
- 선행 조건: x402 정산 end-to-end 완주 (Spike A/B faucet 인간 게이트) — 미완주 시 P0-P2는 mock 정산으로 진행 가능
- Kill criteria: Phase당 주말 2회 초과 지연 → 해당 Phase "design note + simulated demo" 피벗 (v1 원칙 승계)
- [ ] 자율성 욕구 agent 통합 (별도 프로젝트 가능)
- [ ] 공개 A2A 마켓플레이스 지원
- [ ] 월간 성격 테스트 ritual
- [ ] Importance-score 기반 reflection trigger
- [ ] DuckDB WAL 모드 + 정기 백업
