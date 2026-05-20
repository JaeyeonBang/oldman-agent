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
- [ ] EVAL-1 live baseline capture (실제 Haiku 호출, jaccard 기록) → `ANTHROPIC_API_KEY` 설정 후 실행
- [ ] EVAL-2 live baseline capture (실제 Haiku judge, hallucination rate 기록) → `ANTHROPIC_API_KEY` 설정 후 실행

## M1 Engineering Review tasks (apply during Phase 1.x)

- [ ] **T1 (P1)** Add UNIQUE constraint on `events.payload_hash` + IntegrityError handling → race-safe dedup
- [ ] **T2 (P1)** Wrap `publish()` handler in explicit BEGIN/COMMIT/ROLLBACK transaction → L0/L1 consistency
- [ ] **T3 (P1)** Specify + test `tokenize` edge cases (empty / unicode-Korean / numeric / boolean / null)
- [ ] **T4 (P1)** Regression test: concurrent same-hash insert returns exactly 1 success + 1 conflict
- [ ] **T5 (P2)** README: `uvicorn --workers 1` mandatory + DuckDB single-writer rationale
- [ ] **T6 (P2)** ASCII diagrams in `app/api/publish.py` + `app/storage/dedup.py` top-of-file
- [x] **T7 (P2)** Sync TODOS.md with new PRD milestones — DONE
- [ ] **T8 (P3)** A2A SDK pub/sub spike deferred to M2 entry checklist (was M1 60-min budget)

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

- [ ] Outbound x402 (pay-to-share) — `spikes/outbound_x402.py` scaffold 재활용
- [ ] Inbound ap2+x402 (pay-to-query)
- [ ] L0 gate (Haiku triage 등) — dogfood 데이터 보고 도입 여부 결정
- [ ] Sleep-time precompute — top-3 query pattern 측정 후
- [ ] Rolling credibility window — 결제 stake 생긴 후
- [ ] OpenRouter 실제 비용 driven swap (메트릭 확보 후)

## v2 (deferred)

- [ ] Reputation system + deferred payout (TraceRank-style)
- [ ] 자율성 욕구 agent 통합 (별도 프로젝트 가능)
- [ ] 공개 A2A 마켓플레이스 지원
- [ ] 월간 성격 테스트 ritual
- [ ] Importance-score 기반 reflection trigger
- [ ] DuckDB WAL 모드 + 정기 백업
