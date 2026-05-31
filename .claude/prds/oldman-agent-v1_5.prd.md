# oldman_agent v1.5 — 양방향 결제 토폴로지 통합 (PRD)

Generated 2026-05-31 by Opus. Sequel to v1 PRD (`oldman-agent-v1.prd.md`) and v2 PRD (`oldman-agent-v2.prd.md`).

**Status**: **DRAFT → α/β SPLIT** (per `/plan-eng-review` Step 0 scope challenge 2026-05-31). v1.5α (mock-only, G1-G6, ~5h) ships first to test hypothesis cheap; v1.5β (real x402 + admin endpoint + smoke script, G7, ~5h) follows after K1 evaluation gate.

**Relation to prior PRDs**:
- v1 (Option A memory) + v2 (A2A v0.3 messaging) **stay**. v1.5 is **additive**.
- v1.5 implements the deferred payment layer that v1 PRD §97 calls out (`v1.5 (이 PRD 범위 밖, 후속 PRD로 분리)`).
- Both spikes (Spike A outbound x402, Spike B inbound ap2+x402) are **verified to the buyer-faucet boundary** as of 2026-05-31 — see `spikes/spike_a_outcome.md` + `spikes/spike_b_outcome.md`. v1.5 is integration, not exploration.

---

## 1. Problem

v1+v2가 ship된 상태에서 dogfood 데이터를 모으는 중이나, **설계의 핵심 차별점인 "양방향 결제 토폴로지"가 코드에 미통합** — Spike만 있고 production path는 free publish + free query다. 이 상태에서는:

1. **Spam 가설 미검증** — v1 PRD risk #3 "spam economics (MED)"는 결제 도입을 전제로 해결되도록 설계됐다. payment 없이는 rate-limit + dup-hash가 진짜 효과적인지 측정 불가.
2. **정보 가치 차등 미관측** — 어떤 publish가 비싸고 어떤 query가 비싼지 운영자가 wallet usage로 정량 관측할 경로가 없다.
3. **Design "whoa"가 demo 영상에 안 잡힘** — "정보를 사들이고 narrative로 되판다"는 핵심 unique selling point가 free path에선 시각화 안 됨.

## 2. Evidence

- **Strong**: Spike A — `GET /publish-info` 402 + valid x402 v2 challenge (USDC Base Sepolia, scheme=exact) live verified 2026-05-31.
- **Strong**: Spike B — `POST /invoice` 200 + ap2 IntentMandate + W3C PaymentRequest + `POST /query` 402 live verified 2026-05-31.
- **Strong**: x402 + ap2 Python SDK 모두 stable + Py 3.11 지원 (`x402[httpx,evm]==2.12.0`, `ap2==0.1.1`).
- **Assumption — needs dogfood**: 실제 데모 네트워크 에이전트들이 publish/query 시 wallet 보유 + funding 부담을 감내할지 (vs free path 선호).
- **Weak**: 최적 단가 (0.001 USDC publish reward vs 0.001 USDC query price)는 v1.5 ship 후 메트릭으로 튜닝 — design doc §120 ack한 unresolved.

## 3. Users

- **Primary**: 동일 — A2A 데모 네트워크 operator. v1.5에서 추가되는 surface는 (a) 본인 wallet 1개 세팅, (b) demo 영상에서 결제 시각화, (c) `/admin/payments` 메모리 확장.
- **Secondary**: external buyer agent (query 발신자) — wallet 필수. v1에서는 optional이었음.
- **Not for**: 자율성 agent, 공개 마켓플레이스 (v2), 다중 통화 (v2), 익명 무결제 query (v1 잔존 경로).

## 4. Hypothesis

우리는 **양방향 micropayment(pay-to-share + pay-to-query) 도입**이 **demo 네트워크의 (a) spam을 자연 감소시키고 (b) 정보 가치 차등을 wallet 메트릭으로 관측 가능하게** 한다고 믿는다.

**v1.5 ship 후 1주일 내 본인이 실 wallet으로 publish≥3 (총 ≥ 0.003 USDC outbound) + query≥3 (총 ≥ 0.003 USDC inbound revenue) 자발 실행**하면 옳음을 알게 된다. 이게 안 되면 결제 도입은 friction이 가치를 초과한 것이므로 cinematic-mock 피벗.

## 5. Success Metrics

| Metric | Target | How measured |
|---|---|---|
| **Real-payment e2e** | Spike A + B 각 1건 on Base Sepolia 성공 | `events.payment_id IS NOT NULL` ≥ 1, `invoices.status='settled'` ≥ 1 |
| **Mock-payment integration** | publish + query 둘 다 mocked x402 client로 happy path + 실패 path 통과 | 신규 integration tests (C1-C4 §9) |
| **No regression on free** (transition) | `payment_required=false` config일 때 v1/v2 동작 100% 보존 | 기존 291 test 그대로 PASS |
| **Spam 가설 1차 검증** | dogfood 1주 후 publish/query 단가가 spam 시도를 막는지 정성 회고 | DESIGN_NOTES.md update |
| **Wallet UX 부담** | 운영자 setup 시간 ≤ 30분 (faucet 포함) | README walkthrough self-time |
| **Time-to-ship cap** (kill) | 2 주말(~10h) | 캘린더 |

## 6. Scope

### MVP (v1.5α) — mock-first integration, ~5h CC

> **Scope 결정 근거 (α split, 2026-05-31)**: `/plan-eng-review` Step 0 complexity check가 11 files + 6 new classes를 trigger했고 사용자가 α/β split을 채택. α는 **hypothesis 검증에 필수인 항목만** 포함 — mock으로 양방향 결제 통합 가능성을 cheap+fast 입증. K1 (1주 dogfood 결제 0건) 데이터를 α만으로 수집 → β work sunk cost 절감 옵션.

1. **DB schema 확장** (migration 002):
   - `events` 테이블에 `payment_id VARCHAR NULL`, `amount VARCHAR NULL`, `asset VARCHAR NULL`, `network VARCHAR NULL`, `tx_hash VARCHAR NULL` 추가. 모두 nullable — free path가 유지되므로 NULL 허용 필수.
   - 신규 `invoices` 테이블 — `invoice_id PK, query TEXT, subject_agent NULL, intent_expiry TIMESTAMP, status ENUM(pending|settled|expired|invalidated), payment_id NULL, issued_at, settled_at NULL`.
   - 신규 인덱스: `idx_events_payment_id`, `idx_invoices_status_expiry`.
2. **Payment Adapter (mock only)** (`app/payment/`)
   - `app/payment/base.py` — `PaymentClient` Protocol, `PaymentReceipt`/`PaymentError` 타입.
   - `app/payment/mock.py` — `MockPaymentClient` — config-driven outcome 시뮬레이션 (success / network_error / insufficient_funds / timeout / double_spend).
   - `MockPaymentMiddleware` — A2A executor 안에서 invoice settle을 mock으로 즉시 처리. real x402 PaymentMiddlewareASGI는 v1.5β.
   - **Config toggle**: `config/payment.yaml` → `enabled: bool`, `mode: mock`, `prices: {publish_reward, query_price}`. `enabled=false`일 때 v1/v2 코드 path 그대로.
3. **Publish 경로 변경** (`app/api/publish.py`):
   - `payment_enabled=true` → `MockPaymentClient.pay()` 호출.
   - 결제 실패 → `PaymentError` raise → 기존 transaction의 ROLLBACK 경로 활용 (event 미저장).
   - 결제 성공 → `payment_id, amount, asset, network, tx_hash` 컬럼 채워 event INSERT.
4. **Query 경로 변경** (`app/a2a/executor.py` query intent dispatch):
   - `payment_enabled=true`: query intent 도착 → `invoices` 테이블에 pending row + ap2 IntentMandate 합성 → `MockPaymentMiddleware`가 settled 마킹 후 narrative 진입.
   - timeout: invoice expiry 지나면 status='expired' 자동 마킹 (background cleanup task).
5. **Config + Bootstrap** — `app/bootstrap.py` 확장: `PaymentClient` factory (mock only). `mode=real` 또는 키 시도 시 v1.5β 미구현 명시.
6. **`spikes/outbound_x402.py` / `spikes/inbound_ap2.py` reuse** — spike 코드 자체는 docs/reference로 남기고, v1.5α는 spike 패턴을 내부화한 mock 어댑터만.
7. **Tests** (G1-G6):
   - **Unit** — `MockPaymentClient` 5 케이스 (success, network_error, insufficient_funds, timeout, double_spend). dedup race-safety regression (v2.5 T4) 결제 layer에서도 유지.
   - **Integration** — A2A executor를 mocked PaymentClient + mocked Middleware로 호출 → publish/query 6 케이스 (free, mock paid, mock failed, settled, expired, race).
   - **Backward compat regression** — `payment_enabled=false` config로 기존 291 tests 그대로 PASS.

### v1.5β — real client + live smoke + admin endpoint, ~5h CC (deferred)

α가 K1 통과 (dogfood 결제 동기 입증) 후 진입:

1. **`app/payment/x402.py`** — `X402PaymentClient` (real EVM/Base Sepolia client wrapping `spikes/outbound_x402.py` `pay_and_fetch()` 패턴).
2. **`X402PaymentMiddlewareIntegration`** — real `x402.http.middleware.fastapi.PaymentMiddlewareASGI`를 A2A executor에 wire.
3. **`config/payment.yaml`** `mode=real` 활성화 + `wallet.{key_env, receive_address_env}` 로드.
4. **`app/api/admin.py`** `/admin/memory` 확장 — `payments_total` (settled USDC), `invoices_pending`, `outbound_spent` (token-guarded).
5. **`scripts/payment_smoke.sh`** — Base Sepolia 1건씩 e2e (publish + query) 매뉴얼 검증.
6. **G7 live smoke** — `scripts/payment_smoke.sh`가 ship gate 추가.
7. **Demo 영상 갱신** — 양방향 결제 시각화 1분 (Spike A 스크린샷 + Spike B 인보이스 JSON + wallet 잔액 변화).

### Out of Scope (v1.5)

| Item | Why deferred |
|---|---|
| Reputation system + deferred payout | v2 — 결제 도입 후 spam 패턴 실측한 다음 설계 |
| Multi-asset (USDC만 v1.5) | v2 — ETH-mainnet bridge, EURC 등은 demo 가치 대비 노력 큼 |
| Public marketplace registry | v2 — 동의 기반 작은 네트워크가 v1 가정 |
| Wallet rotation / multi-sig | v2 — single hot wallet for demo |
| Refund/dispute | v2 — `refund_period=0` (ap2 invoice) 명시. 잘못된 결제 = 잃은 결제 (demo 정책) |
| 자율성 agent 통합 | 별도 프로젝트 |
| 익명 무결제 query를 정책으로 허용 | v1.5는 binary: enabled=true → 결제 필수, enabled=false → v1/v2 동작. 부분 free는 v2에서 reputation 도입 시 |

## 7. Architectural decisions (D-series)

- **D1 — Migration 별도 파일**: schema 변경은 `migrations/002_payments.sql` 신규. 기존 001 수정 금지 (v2.5 race-safety constraint들 보존).
- **D2 — Payment adapter는 protocol-based**: `app/payment/base.py`에 `PaymentClient` Protocol. mock/real을 dependency injection으로 교체. 기존 `app/llm/router.py` 패턴 재활용.
- **D3 — Settlement state는 `invoices` 테이블로 격리**: `events`에 결제 컬럼을 추가하긴 하지만, payment lifecycle (pending → settled → expired)은 별도 테이블로. 이렇게 안 하면 events 테이블이 mutable해져서 append-only invariant 깨짐.
- **D4 — Outbound payment는 BEGIN TX 안에서**: publish의 race-safety 트랜잭션 안에 outbound x402 호출도 포함. 결제 실패 → ROLLBACK으로 자연 처리. 트랜잭션 길이 증가 (~1-3초) 감수.
- **D5 — Inbound query는 invoice → settlement → narrative 3단계**: 한 트랜잭션에 묶지 않음 (settlement는 외부 facilitator 의존). 각 단계가 별도 DB write.
- **D6 — Mock = default, Real = explicit opt-in**: 신규 운영자가 키 없이도 v1.5 코드 path를 돌려볼 수 있도록 `mode=mock`이 default. `mode=real`은 `OLDMAN_PAYMENT_REAL=true` + wallet key 둘 다 필요.
- **D7 — Backward compat**: `payment_enabled=false`이면 v1/v2 동작 100% 보존. 모든 신규 컬럼 NULL 허용. 모든 신규 테이블 비어 있어도 조회 안전.

## 8. Pivot triggers + Kill criteria

상속: v1 PRD §49 pivot rule + kill criteria 그대로 적용.

추가:
- **P1**: mock-level integration tests 4개 케이스가 1 주말 내 다 안 통과 → cinematic-mock 피벗 (production wiring 보류, demo만 시연).
- **P2**: 운영자(본인) wallet setup이 1시간 넘게 걸림 → wallet UX 친절도 강화 또는 mock-only 모드 잠시 ship.
- **K1**: dogfood 1주 후 결제 1건도 자발 실행 안 됨 → v1.5 archive, design note에 "결제 friction이 가치 초과" 회고.

## 9. Acceptance gates

기존 291 tests + EVAL gates 모두 PASS 유지하고, 신규로:

| Gate | What it proves |
|---|---|
| **G1** Unit: `MockPaymentClient` 5 케이스 (success, network_error, insufficient_funds, timeout, double_spend) | adapter contract 명확함 |
| **G2** Integration: `payment_enabled=true` + mock client + publish → event row with `payment_id` populated, mock invoice never created | outbound path wired |
| **G3** Integration: outbound mock 실패 → ROLLBACK, events row count 변화 0 | failure path safe |
| **G4** Integration: `payment_enabled=true` + mock middleware + query → invoice issued (status='pending') → mock settle → narrative returned | inbound 3단계 작동 |
| **G5** Integration: query invoice expiry 도달 → background cleanup이 status='expired' 갱신 | timeout handling |
| **G6** Regression: `payment_enabled=false` config로 기존 291 test 전부 PASS | backward compat 명문화 |
| **G7** Live smoke (optional, faucet-gated, manual): Base Sepolia 1건 publish + 1건 query e2e — `payment_smoke.sh` 한 명령 | real wallet path 작동 |

**Ship 조건**: G1-G6 전부 PASS (G7은 release notes에 "live smoke skipped on this build" 명시 가능).

## 10. Open questions (for `/plan-eng-review`)

1. **Wallet 1개 공용 vs 에이전트별 분리?** v1.5 default는 oldman의 1개 wallet만 (operator hot wallet). 에이전트별 wallet은 wallet management 복잡도 추가 — v2.
2. **Outbound x402가 transaction 안에 들어가도 안전한가?** facilitator 응답 latency 2-5s 동안 DuckDB transaction이 열려 있어도 single-writer 환경에서 OK인가? alternative: transaction 밖에서 결제 → 성공 후 transaction → race 위험.
3. **Invoice를 events 테이블에 join할 필요가 있나?** query 응답에 인용된 event_id list가 있고, 그 narrative에 대한 settlement record가 invoices에 있음. 두 테이블 join은 reporting에만 필요 — DDL 결정 미룰지.
4. **Per-query pricing?** 초안: flat 0.001 USDC. variance (length-based, tier-based)는 metric 본 후 v2.
5. **AgentCard 확장**: pay-to-query enabled 표시를 `x-oldman.payment` extension에 넣는가? A2A 표준 외 확장이라 client compat 영향 0이긴 함.

## 11. Implementation order

### v1.5α (this PRD, ~5h CC)

1. **Migration 002 + DB layer 확장** (1.5h) — schema 변경 + payment helper. G1-G2 unit RED 먼저.
2. **`app/payment/{base,mock}.py` 모듈 신설** (1h) — `PaymentClient` Protocol + `MockPaymentClient` only. G1 GREEN.
3. **`app/api/publish.py` outbound mock integration** (1h) — config-toggled call site. G2/G3 GREEN.
4. **`app/a2a/executor.py` query invoice + mock settlement gate** (1h) — ap2 invoice 발행 + mock middleware + 3단계 dispatch. G4/G5 GREEN.
5. **Bootstrap + config wiring** (0.5h) — `config/payment.yaml` (mock only), bootstrap factory.
6. **Backward compat regression** (0.5h) — G6 보장. `payment_enabled=false`로 기존 291 test 그대로.

→ Ship gate: G1-G6 PASS. K1 (dogfood 1주 결제 시도 0건) 평가 시작.

### v1.5β (deferred PRD addendum, ~5h CC, K1 통과 후 진입)

7. **`app/payment/x402.py`** (2h) — real x402 client wrapping spike. G7 RED.
8. **executor.py real PaymentMiddlewareASGI integration** (1h) — mock→real swap. G7 GREEN with mock fallback path.
9. **`config/payment.yaml`** real mode + `app/bootstrap.py` wallet load (0.5h).
10. **`app/api/admin.py` `/admin/memory` 확장** (0.5h) — payments stats.
11. **`scripts/payment_smoke.sh` + README walkthrough** (0.5h) — manual Base Sepolia e2e.
12. **Demo 영상 갱신** (0.5h, optional) — 사용자 단계.

→ Ship gate: G7 live smoke 1회 성공.

**Pivot decision point** (between α and β): K1 fired (no real payment after 1 week dogfood) → β archive + DESIGN_NOTES.md 회고. 그렇지 않으면 β 진행.

---

## Appendix A — schema (migrations/002_payments.sql draft)

```sql
-- 002: payments + invoices for v1.5 양방향 결제 토폴로지.

ALTER TABLE events ADD COLUMN payment_id  VARCHAR;
ALTER TABLE events ADD COLUMN amount      VARCHAR;
ALTER TABLE events ADD COLUMN asset       VARCHAR;
ALTER TABLE events ADD COLUMN network     VARCHAR;
ALTER TABLE events ADD COLUMN tx_hash     VARCHAR;
CREATE INDEX IF NOT EXISTS idx_events_payment_id ON events(payment_id);

-- A1-A (eng-review 2026-05-31): partial-payment row 차단.
-- payment_id가 있으면 amount/asset/network/tx_hash도 모두 NOT NULL (v2.5 race-safety
-- UNIQUE backstop과 같은 정신으로 schema 레이어에서 invariant 강제).
-- DuckDB CHECK는 row-insert/update 시점 평가됨.
ALTER TABLE events ADD CONSTRAINT events_payment_complete CHECK (
  payment_id IS NULL
  OR (amount IS NOT NULL AND asset IS NOT NULL
      AND network IS NOT NULL AND tx_hash IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS invoices (
  invoice_id      UUID PRIMARY KEY,
  query           TEXT NOT NULL,
  subject_agent   VARCHAR,
  intent_expiry   TIMESTAMP NOT NULL,
  status          VARCHAR NOT NULL CHECK (status IN ('pending','settled','expired','invalidated')),
  payment_id      VARCHAR,
  issued_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  settled_at      TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invoices_status_expiry ON invoices(status, intent_expiry);
```

## Appendix B — config (config/payment.yaml draft)

```yaml
# v1.5 default — mock-only, fully backward compatible.
enabled: false
mode: mock                    # mock | real

wallet:
  key_env: EVM_PRIVATE_KEY    # only read when mode=real
  receive_address_env: EVM_RECEIVE_ADDRESS

prices:
  publish_reward_usdc: 0.001  # outbound paid to source agent on publish
  query_price_usdc:    0.001  # inbound paid by querier

network: eip155:84532          # Base Sepolia
asset:   "0x036CbD53842c5426634e7929541eC2318f3dCF7e"   # USDC on Base Sepolia
facilitator_url: https://x402.org/facilitator

invoice_ttl_seconds: 300       # 5min
cleanup_interval_seconds: 60   # background expiry sweep
```

## Appendix C — links

- `~/.gstack/projects/oldman_agent/qkdwodus777-unknown-design-20260518-231759.md` — original design doc (D-series + payment topology motivation)
- `.claude/prds/oldman-agent-v1.prd.md` — v1 baseline (memory + persona)
- `.claude/prds/oldman-agent-v2.prd.md` — v2 (A2A v0.3 messaging compliance)
- `spikes/spike_a_outcome.md` — outbound x402 verified to boundary
- `spikes/spike_b_outcome.md` — inbound ap2+x402 verified to boundary
- `eval/baselines/v2.5_live_baseline.md` — current EVAL state going into v1.5

---

## Eng-review findings (2026-05-31)

Scope challenge reduced 11 files → 9 (split α/β). Remaining architecture / code / test / perf review applied per user "권장안 진행" directive — recommendations applied inline, listed here for audit:

### Architecture (4 findings)

- **A1 — events 결제 invariant 강제** (P1) — APPLIED: CHECK constraint `events_payment_complete` (Appendix A) prevents partial-payment row insertion. payment_id 있으면 amount/asset/network/tx_hash 모두 NOT NULL. v2.5 UNIQUE backstop과 같은 schema-layer enforcement 패턴.
- **A2 — `invoices.payment_id` FK to events not enforced** (P2) — KEEP NULLABLE NO-FK. v1.5α 단계에서는 invoices.payment_id가 events.payment_id 또는 미래 payments.payment_id를 가리킬 수 있어 어느 쪽도 FK 가능. v1.5β real client 도입 시 다시 평가.
- **A3 — Outbound payment in BEGIN/COMMIT TX (D4)** (P1) — KEEP IN-TX (v1.5α): mock client는 즉시 반환이라 latency 0. v1.5β real client 도입 시 facilitator 2-5s 응답이 DuckDB single-writer를 막아 다른 publish가 대기 → β PRD에 명시적 재평가 트리거 추가 필요. **β open question 추가됨**.
- **A4 — Background invoice cleanup task** (P2) — APPLIED via §6.4: `cleanup_interval_seconds: 60` (Appendix B). asyncio background task with `OldmanAgentExecutor` lifecycle. expiry 도달 시 `UPDATE invoices SET status='expired' WHERE status='pending' AND intent_expiry < NOW()`. background task 실패 시 silent → /admin/memory의 `invoices_pending` 메트릭으로 가시화 (β phase).

### Code quality (2 findings)

- **C1 — `PaymentClient` Protocol vs base class** (P2) — APPLIED: Python `typing.Protocol` (PEP 544, structural subtyping). 기존 `app/llm/base.py`의 `LLMProvider` 패턴과 일치. mypy strict + duck typing 양쪽 만족.
- **C2 — Top-of-file ASCII diagram** (P3) — APPLIED: 신규 `app/payment/base.py` + `app/payment/mock.py`에 v2.5 publish.py/dedup.py 스타일 ASCII pipeline diagram 의무. 양방향 결제 흐름은 publish/query 모듈 docstring에도 반영.

### Tests (G1-G6 coverage map)

```
v1.5α coverage targets (mock-only, ship gate G1-G6)

[+] app/payment/base.py
  └── PaymentClient.pay()                            [G1 → ★★★]

[+] app/payment/mock.py
  ├── MockPaymentClient(outcome="success")           [G1 → ★★★]
  ├── MockPaymentClient(outcome="network_error")     [G1 → ★★★]
  ├── MockPaymentClient(outcome="insufficient_funds")[G1 → ★★★]
  ├── MockPaymentClient(outcome="timeout")           [G1 → ★★★]
  └── MockPaymentClient(outcome="double_spend")      [G1 → ★★★]

[+] app/api/publish.py (modified)
  ├── execute_publish() with payment_enabled=false   [G6 → ★★★] (backward compat)
  ├── execute_publish() with mock success            [G2 → ★★★ → events.payment_id set]
  ├── execute_publish() with mock failure            [G3 → ★★★ → ROLLBACK, 0 rows]
  └── concurrent same-hash + mock (v2.5 T4 regression) [REGRESSION CRITICAL → ★★★]

[+] app/a2a/executor.py query path (modified)
  ├── query intent + payment_enabled=false           [G6 → ★★★]
  ├── query intent + mock middleware → invoice issued [G4 → ★★★ → invoices status='pending']
  ├── mock settle → narrative returned                [G4 → ★★★ → status='settled']
  └── invoice expiry → background cleanup            [G5 → ★★★ → status='expired']

[+] config/payment.yaml + bootstrap
  ├── enabled=true + mode=mock → MockPaymentClient   [G2/G4 → ★★]
  └── enabled=true + mode=real (v1.5α) → fail-fast   [G6 → ★★★]

Critical regression (REGRESSION RULE):
  v2.5 T4 concurrent-same-hash test must still PASS with payment_enabled=true
  in mock mode (both calls hit mock → exactly 1 success + 1 dedup + 1 row).

COVERAGE: 14/14 paths targeted (100%) — α scope.
```

### Performance (1 finding)

- **P1 — Mock client latency contract** (P3) — APPLIED: `MockPaymentClient` `pay()` returns immediately (no sleep). real client (β) facilitator latency 2-5s가 publish TX를 점유하는 문제는 β PRD에 reserved (A3와 동일 root cause).

### NOT in scope (v1.5α)

| Item | Rationale | Where it goes |
|---|---|---|
| Real `X402PaymentClient` | α는 mock-only로 hypothesis 검증 cheap. | v1.5β |
| `/admin/memory` payments stats | reporting addon, hypothesis 측정과 무관. | v1.5β |
| `scripts/payment_smoke.sh` | live wallet 없이는 의미 없음. | v1.5β |
| Per-agent wallet management | demo scope에 1 hot wallet 충분. | v2 |
| Refund/dispute | demo 정책: 잘못된 결제 = 잃은 결제. | v2 |
| Reputation + deferred payout | spam 패턴 측정 후. | v2 |
| Multi-asset (ETH/EURC) | USDC만 v1.5 ship. | v2 |
| Public marketplace registry | 동의 기반 작은 네트워크가 v1 가정. | v2 |

### What already exists

| Sub-problem | Existing code | Reuse? |
|---|---|---|
| Outbound x402 payment | `spikes/outbound_x402.py` `pay_and_fetch()` | v1.5β `app/payment/x402.py`가 내부화 |
| Inbound ap2 invoice + x402 gate | `spikes/inbound_ap2.py` | v1.5α invoice 합성 로직 + v1.5β real middleware reuse |
| Transaction + ROLLBACK | `app/api/publish.py:157-202` (v2.5) | v1.5α outbound mock call이 TX 내부에 들어감 — 기존 ROLLBACK 패턴 그대로 |
| Schema migration runner | `app/storage/db.py::apply_migrations` | migration 002 자동 적용 |
| A2A executor query dispatch | `app/a2a/executor.py::_dispatch_query` | invoice/settle 3단계 wrapping 만 추가 |
| `/admin/memory` token-guard | `app/api/admin.py` (v2.1) | v1.5β payments stats 동일 패턴 |

### Failure modes (v1.5α critical scan)

| Path | Failure | Test? | Error handling? | User sees? | Verdict |
|---|---|---|---|---|---|
| publish outbound mock | mock returns PaymentError | G3 ✓ | ROLLBACK ✓ | A2A executor → Task ack failed ✓ | OK |
| query invoice issuance | invoices INSERT fails | G6 regression ✗ | TX ROLLBACK 적용 안 됨 (별도 statement) | "내가 못 봐서 모르겠네" fallback? | **gap** |
| mock middleware settle | background cleanup race (settle + cleanup 동시) | G5 ✓ | UPDATE ... WHERE status='pending' 조건문이 race-safe | none | OK |
| config wiring | enabled=true + mode=real (v1.5α 미구현) | G6 ✓ | fail-fast on bootstrap | startup error log | OK |

**gap (P2 follow-up TODO)**: query 경로에서 invoices INSERT 실패 시 narrative 응답이 일관되게 fallback에 도달하는지 확인 필요. invoices write 실패가 silent 가능. v1.5α 구현 시점에 G4 테스트에 negative case 추가 권장 — implementation phase에서 catch.

### Worktree parallelization

Sequential implementation, no parallelization opportunity. v1.5α 6 steps는 dependency chain (schema → adapter → publish/query → bootstrap → regression)이라 single worktree에서 순차 진행. v1.5β만 별도 worktree 가능 (β real client + admin endpoint는 α 끝난 후).

### Implementation Tasks (synthesized from findings)

- [ ] **T1 (P1, human: ~30min / CC: ~5min)** — schema/migrations — Apply A1-A CHECK constraint `events_payment_complete` to migration 002
  - Surfaced by: Architecture A1
  - Files: `app/storage/migrations/002_payments.sql`
  - Verify: `pytest tests/unit/test_dedup.py tests/integration/test_smoke.py` (CHECK 추가 후 기존 ROW 영향 0 확인)
- [ ] **T2 (P1, human: ~1h / CC: ~15min)** — payment — `PaymentClient` Protocol + `MockPaymentClient` 5 outcome cases
  - Surfaced by: Code C1, Test G1
  - Files: `app/payment/base.py`, `app/payment/mock.py`, `tests/unit/test_payment_mock.py`
  - Verify: `pytest tests/unit/test_payment_mock.py -v`
- [ ] **T3 (P1, human: ~1.5h / CC: ~20min)** — api — publish.py outbound mock integration with rollback
  - Surfaced by: Architecture A3 (mock path), Test G2/G3
  - Files: `app/api/publish.py`, `tests/integration/test_publish_payment.py`
  - Verify: G2 + G3 + v2.5 T4 regression pass
- [ ] **T4 (P1, human: ~2h / CC: ~25min)** — a2a — executor query invoice + mock settlement + expiry cleanup
  - Surfaced by: Architecture A4, Test G4/G5
  - Files: `app/a2a/executor.py`, `app/storage/invoices.py` (new), `tests/integration/test_query_payment.py`
  - Verify: G4 + G5 pass; gap (invoices INSERT failure path) negative test 포함
- [ ] **T5 (P2, human: ~30min / CC: ~5min)** — config — `config/payment.yaml` + bootstrap factory + fail-fast for v1.5β modes
  - Surfaced by: Test G6, Architecture (config toggle)
  - Files: `config/payment.yaml`, `app/bootstrap.py`, `tests/unit/test_bootstrap_payment.py`
  - Verify: G6 regression — 291 existing tests still pass with `payment_enabled=false`
- [ ] **T6 (P3, human: ~15min / CC: ~5min)** — docs — Top-of-file ASCII pipeline diagrams in `app/payment/base.py` + `app/payment/mock.py`
  - Surfaced by: Code C2
  - Files: `app/payment/base.py`, `app/payment/mock.py`
  - Verify: `ruff check` clean (docstring rendering only)

Total estimate v1.5α: ~5h CC, ~5.5h human (matches Step 0 split decision).

### Unresolved decisions

(none in this review — all flagged items either APPLIED or explicitly deferred to v1.5β / v2)

### Outside voice

Skipped — user directive "권장안 진행" + already running near tool-call budget. Optional /codex consult available if user wants adversarial sweep before implementation.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | scope α/β split applied; 4 arch + 2 code + 1 perf findings — all APPLIED or DEFERRED |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **UNRESOLVED:** 0
- **VERDICT:** ENG CLEARED (PLAN) — v1.5α ready to implement. Codex consult optional, not required.
