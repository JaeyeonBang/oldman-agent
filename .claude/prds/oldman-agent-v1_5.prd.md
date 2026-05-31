# oldman_agent v1.5 — 양방향 결제 토폴로지 통합 (PRD)

Generated 2026-05-31 by Opus. Sequel to v1 PRD (`oldman-agent-v1.prd.md`) and v2 PRD (`oldman-agent-v2.prd.md`).

**Status**: **DRAFT → CREDITS PIVOT** (2026-05-31 — outside voice critique accepted). v1.5α uses **off-ledger credits ledger** (in-process, no chain) to test the bidirectional payment hypothesis cheaply and *meaningfully*. v1.5β layers x402+ap2 on top as cinematic real-payment showcase — strictly optional, demo-video driven, cancellable on K1.

**Why pivoted from prior α (mock x402)**: The mock client returns string-coded errors instantly and never exercises the *interesting* failure modes (facilitator instability, on-chain latency, faucet drying, nonce collisions). It tests code paths, not the system. Worse, K1 (1 week dogfood, 0 real payments) was structurally unfalsifiable under mock-α because there was no real-payment surface to attempt. Credits cuts the indirection: every publish + every query touches a real ledger, K1 becomes "credits actually moved," and the hypothesis test stops depending on infrastructure we don't control.

**Relation to prior PRDs**:
- v1 (Option A memory) + v2 (A2A v0.3 messaging) **stay**. v1.5 is **additive**.
- v1.5 implements the deferred payment layer that v1 PRD §97 calls out.
- Spike A + B (verified 2026-05-31 — `spikes/spike_a_outcome.md`, `spikes/spike_b_outcome.md`) remain useful: they prove the x402/ap2 stack works, which v1.5β will rely on. v1.5α intentionally bypasses them so we can validate the *design* before paying the *infrastructure cost*.

---

## 1. Problem

v1+v2가 ship된 상태에서 dogfood 데이터를 모으는 중이나, **설계의 핵심 차별점인 "양방향 결제 토폴로지"가 코드에 미통합** — 페이먼트 인프라(x402/ap2)는 Spike에 있고, production path는 free publish + free query다. 이 상태에서는:

1. **Spam 가설 미검증** — payment friction이 dup-hash + jaccard 가드보다 실효 있는지 측정 불가.
2. **정보 가치 차등 미관측** — 어떤 publish/query가 비싸고 싼지 객관 메트릭 없음.
3. **Design "whoa"가 demo 영상에 안 잡힘** — "정보를 사들이고 narrative로 되판다"는 핵심 unique selling point가 free path에선 시각화 안 됨.

**Outside voice critique (2026-05-31, accepted)**:
- N=1 operator dogfood에서 "spam 가설"은 자기 자신을 spam하지 않으므로 unfalsifiable. → α를 multi-agent simulation으로 reframe.
- 양방향 결제는 코드 상 두 개의 독립 paywall — narrative differentiator지 architectural differentiator 아님. → α가 narrative test로 정직히 라벨링.
- Mock x402 client는 "code 분기" 검증이지 "system" 검증 아님. 진짜 위험(facilitator 5xx, on-chain latency, nonce, faucet)은 안 잡힘. → α를 chain 의존 없는 ledger로 옮겨, 가설 자체를 cheap+sharp 테스트.

## 2. Evidence

- **Strong**: Spike A + B 모두 verified-to-challenge-boundary (2026-05-31) → x402/ap2 인프라는 작동. v1.5β 진입 시 재활용 가능.
- **Strong**: v2.5 race-safety transaction pattern (`app/api/publish.py:157-202`)이 이미 in-place — credits ledger의 atomic transfer도 같은 패턴으로 보장.
- **Strong**: DuckDB single-writer 환경에서 in-process credits 테이블은 facilitator-style outage risk 0, latency variance 0.
- **Assumption — needs dogfood**: 운영자가 multi-agent 시뮬레이션으로 credits 소비 패턴을 의도적으로 차등 주입할지 (vs free path).
- **Weak**: credits 단가 (publish_reward=1, query_price=1 default)는 메트릭 본 후 튜닝.

## 3. Users

- **Primary**: 동일 — A2A 데모 네트워크 operator. v1.5에서 추가되는 surface는 (a) per-agent `credits` 잔액 시각화, (b) demo 영상에서 ledger flow, (c) `/admin/memory` ledger 확장.
- **Secondary**: external buyer agent — credits 잔액 보유 필수. agent 등록 시 starting balance 부여.
- **Not for**: 자율성 agent, 공개 마켓플레이스 (v2), real on-chain micropayments는 v1.5β optional 영상 데모로 한정.

## 4. Hypothesis

우리는 **양방향 internal credits 도입 + per-agent starting balance**가 **demo 네트워크의 (a) spam 시도를 자연 감소시키고 (b) 정보 가치 차등을 ledger 메트릭으로 관측 가능하게** 한다고 믿는다.

**v1.5α ship 후 1주일 내** 다음 조건 둘 다 충족하면 옳음:
- 운영자가 5+ 가상 agent로 시뮬레이션 시 spam-style 행동(반복 publish, dup-hash 우회 시도)이 **credits 소진으로 자연 차단**되는 사례 ≥ 1건.
- 동일 시뮬레이션에서 query당 credits 비용이 narrative 정보 가치(citations 수, persona richness 등)와 **상관 관측** (단순 정량 + 정성 메모 OK).

이 둘 다 안 나오면 가설은 hypothesis도 mechanism도 wrong → archive + DESIGN_NOTES.md 회고. (K1 재정의.)

## 5. Success Metrics

| Metric | Target | How measured |
|---|---|---|
| **Credits ledger functional** | publish + query 각 ≥ 10건이 credits 차감/적립 거쳐 통과 | `credits_transactions` row count |
| **Spam suppression** | dup-hash 우회 시도 ≥ 1건이 잔액 부족으로 차단 | `credits_transactions WHERE outcome='rejected_insufficient_funds'` |
| **Value-differential observability** | query별 cost vs citations count 산점도 1장 | DESIGN_NOTES.md 도표 |
| **No regression on free** | `payment_enabled=false` config일 때 v1/v2 동작 100% 보존 | 기존 291 test 그대로 PASS |
| **Wallet UX 부담** (β only) | β 진입 시 운영자 setup ≤ 30분 | README walkthrough self-time |
| **Time-to-ship cap** (kill) | α: 1 주말(~3h), β: 1 주말(~5h) | 캘린더 |

## 6. Scope

### MVP (v1.5α) — Off-ledger credits, ~2h CC

> **Scope 근거**: outside voice가 지적한 대로, chain stack 없이 양방향 ledger를 in-process로 두면 (1) hypothesis가 unit/integration test로 falsifiable, (2) infrastructure risk 0, (3) demo 영상 시각화는 jq 한 줄로 가능. credits는 demo 정책상 USDC와 1:1 가정 (β로 갈 때 1 credit = 0.001 USDC mapping). **K1이 비로소 의미 있어짐.**

1. **DB schema 확장** (migration 002):
   - 신규 `credits_balances` — `agent_id PK, balance INTEGER NOT NULL DEFAULT 0, last_updated TIMESTAMP NOT NULL`.
   - 신규 `credits_transactions` — `tx_id UUID PK, ts TIMESTAMP NOT NULL, from_agent VARCHAR NULL, to_agent VARCHAR NULL, amount INTEGER NOT NULL, reason VARCHAR NOT NULL CHECK (reason IN ('publish_reward','query_price','starting_grant','admin_adjust','rejected_insufficient_funds')), event_id UUID NULL, invoice_id UUID NULL, outcome VARCHAR NOT NULL CHECK (outcome IN ('applied','rejected_insufficient_funds','rejected_invalid_agent'))`.
   - `events`에 `credits_tx_id UUID NULL` 추가 (FK 강제 안 함 — append-only invariant 보존, T6 outside voice 권고).
   - 인덱스: `idx_credits_tx_ts`, `idx_credits_tx_agent` on `(from_agent, ts DESC)` + `(to_agent, ts DESC)`.
2. **Credits ledger 모듈** (`app/credits/`)
   - `app/credits/ledger.py` — `Ledger.transfer(from_agent, to_agent, amount, reason, *, event_id=None, invoice_id=None) -> CreditsTransaction | InsufficientFundsError` — atomic transfer (DuckDB transaction, race-safe per v2.5 패턴).
   - `app/credits/grants.py` — `apply_starting_grant(agent_id, initial=100)` — agent 첫 publish/query 진입 시 lazy grant.
3. **Publish 경로 변경** (`app/api/publish.py`):
   - `payment_enabled=true` → BEGIN TX 내부에서 `ledger.transfer(from_agent="oldman", to_agent=source_agent, amount=publish_reward, reason="publish_reward", event_id=event_id)`.
   - 잔액 부족 (oldman 측) → InsufficientFundsError raise → ROLLBACK → event 미저장.
   - 성공 → `events.credits_tx_id` 설정 후 INSERT.
4. **Query 경로 변경** (`app/a2a/executor.py` query intent dispatch):
   - `payment_enabled=true`: query 도착 → `invoices` row 발행 (status='pending') → `ledger.transfer(from_agent=querier_agent, to_agent="oldman", amount=query_price, reason="query_price", invoice_id=invoice_id)` 즉시 시도.
   - 성공 → status='settled' → narrative 진입.
   - InsufficientFundsError → status='invalidated' + 즉시 일관된 fallback 응답 ("토큰이 부족하시구먼, 다음에 또 들르시게").
   - expiry는 invoices 테이블에 그대로 유지 (Spike B에서 검증한 ap2 invoice 시간 패턴), background sweep 그대로.
5. **Config + Bootstrap** — `config/payment.yaml` → `enabled: bool`, `mode: credits | x402_real (β)`, `prices: {publish_reward: 1, query_price: 1, starting_grant: 100}`. `enabled=false` 시 v1/v2 동작 100% 보존. **kill-switch env `OLDMAN_PAYMENT_KILL_SWITCH=true`** (outside voice T7c) → 모든 ledger 호출 즉시 noop + log warning, free path로 회귀.
6. **`spikes/inbound_ap2.py` reuse** — invoice 발행 + expiry 로직 패턴 그대로 차용 (단, settlement는 ledger.transfer로 바꿈). spike 코드 자체는 v1.5β reference로 유지.
7. **Tests** (G1-G6 + simulation):
   - **Unit**: `Ledger.transfer` 5 케이스 (success, insufficient_funds, invalid_agent, double-counted, race-safety regression with v2.5 T4 패턴).
   - **Integration**: publish + query 7 케이스 (free path, paid success, paid insufficient, query rejected fallback, invoice expired, concurrent transfer race, kill-switch active).
   - **Backward compat regression**: `payment_enabled=false` 시 기존 291 tests 그대로.
   - **Simulation script** `scripts/credits_sim.py`: 5 가상 agent + dup-hash spam 시도 50건 → 어디서 잔액 부족으로 차단되는지 메트릭 출력. Hypothesis §4 측정 도구.

### v1.5β — x402 + ap2 cinematic real-payment showcase, ~5h CC (deferred + cancellable)

α의 hypothesis가 입증된 후에만 진입. 입증 못 하면 archive + DESIGN_NOTES 회고:

1. **`app/payment/x402.py`** — Spike A `pay_and_fetch()` 내부화. `Ledger.transfer` 대신 real x402 호출 → credits는 mirror 기록만 (β에서 credits = 0.001 USDC 1:1 매핑).
2. **`X402PaymentMiddlewareIntegration`** — Spike B PaymentMiddlewareASGI를 executor에 wire. **Settle-outside-TX 패턴 강제** (outside voice T5): facilitator 호출은 BEGIN TX 밖, 성공 후 ledger transfer + event INSERT를 TX 안.
3. **`config/payment.yaml`** `mode=x402_real` + wallet env.
4. **`app/api/admin.py` `/admin/memory` 확장** — credits balance + recent transactions + (β) on-chain settlement stats.
5. **`scripts/payment_smoke.sh`** — Base Sepolia 1건씩 e2e manual.
6. **G7 live smoke** — 1회 성공 ship gate.
7. **Demo 영상** — credits visualization (α) + real-payment cinematic shot (β) 합본.
8. **Outbound x402 idempotency key** (outside voice T7a) — `payload_hash`를 idempotency key로 재활용 (이미 events.UNIQUE 보장).
9. **EVAL re-baseline trigger** (outside voice T7d) — `publish.py` + `executor.py` 가 EVAL trigger list에 추가됨 (`CLAUDE.md`). β ship gate에 EVAL-2 hallucination rate 재측정 의무.

### Out of Scope (both phases)

| Item | Rationale | Where it goes |
|---|---|---|
| Real on-chain mainnet payments | Base Sepolia testnet only; mainnet은 v2 + audit | v2 |
| Per-agent wallet management | demo scope에 1 hot wallet 충분 | v2 |
| Refund/dispute logic | credits = 잃은 credits (`refund_period=0`). β에 kill-switch만. | v2 |
| Reputation + deferred payout | spam 패턴 실측 후 | v2 |
| Multi-asset (ETH/EURC/etc.) | USDC 1:1 mapping 유지 | v2 |
| Public marketplace registry | 동의 기반 작은 네트워크가 v1 가정 | v2 |
| Cross-agent rolling credibility | v1 PRD에서 이미 deferred | v2 |

## 7. Architectural decisions (D-series)

- **D1 — Migration 별도 파일**: `migrations/002_payments.sql` 신규. 기존 001 수정 금지 (v2.5 race-safety constraints 보존).
- **D2 — Ledger as in-process module, NOT protocol abstraction yet**: α는 1 implementation (DuckDB-backed). β에 도달하면 x402-mirrored ledger도 같은 인터페이스에 들어가지만, α 시점에는 over-abstraction 회피.
- **D3 — `credits_transactions` append-only**: balance는 derived view 또는 cached column. transaction은 immutable log — audit/reporting 친화.
- **D4 — Ledger transfer는 BEGIN TX 안에서**: in-process synchronous라 latency 0. v2.5 race-safety pattern과 같이 single-writer 환경에서 atomic.
- **D5 — Invoice 발행 + settle을 한 트랜잭션에 묶지 않음**: v1.5α는 settle이 ledger.transfer 즉시 → 사실상 atomic이지만, β에 대비해 separation 유지. invoices 테이블은 Spike B 발견 그대로.
- **D6 — Mock = absent; Credits = α default; x402_real = β opt-in**: 신규 운영자가 키 없이도 v1.5α 코드 path를 돌릴 수 있도록 credits가 zero-config default. `mode=x402_real`은 v1.5β 명시 진입.
- **D7 — Backward compat**: `payment_enabled=false`이면 v1/v2 동작 100% 보존. 모든 신규 컬럼 NULL/0 default. 신규 테이블 비어 있어도 안전.
- **D8 — Kill-switch env (outside voice T7c)**: `OLDMAN_PAYMENT_KILL_SWITCH=true` → ledger 모든 호출 noop + warning log. demo 도중 잘못된 transfer pattern 즉시 차단 가능.
- **D9 — Idempotency via existing UNIQUE backstop (T7a)**: outbound 전송에는 idempotency key가 필요하나 α는 in-process라 무관. β는 `payload_hash`를 idempotency key로 reuse — `events.payload_hash UNIQUE`가 이미 보장.
- **D10 — Settle-outside-TX in β (T5)**: real x402 호출은 BEGIN TX **밖**. 성공 후 ledger transfer + event INSERT를 TX 안. facilitator 2-5s latency가 single-writer를 막지 않음.

## 8. Pivot triggers + Kill criteria

- **P1**: α integration tests 7 케이스가 1 주말 내 다 안 통과 → α scope 추가 축소 (simulation script만 떨어뜨림). credits ledger 자체는 1 SQL + 2 함수 + 1 transfer 단위라 가까운 미래에 작동 안 할 시나리오가 낮음.
- **K1 (재정의)**: α ship 후 1주 simulation에서 spam suppression 사례 0건 AND value-differential 관측 0건 → archive + DESIGN_NOTES 회고. (이전 K1은 unfalsifiable이었으므로 폐기.)
- **K2**: α 통과 후 β로 가지 않을 정책 결정 시 β PRD를 명시적으로 cancel. β는 demo cinematic용이지 hypothesis test 아님.

## 9. Acceptance gates

기존 291 tests + EVAL gates 모두 PASS 유지하고, 신규로:

| Gate | What it proves |
|---|---|
| **G1** Unit: `Ledger.transfer` 5 케이스 (success, insufficient, invalid_agent, double-count, v2.5 T4 regression with payment_enabled=true) | ledger contract + race-safety |
| **G2** Integration: `payment_enabled=true` + publish → event row with `credits_tx_id` populated, `credits_transactions` row applied | outbound credit path wired |
| **G3** Integration: publish with `oldman` 잔액 부족 → InsufficientFundsError → ROLLBACK, events count = 0, credits unchanged | failure path safe |
| **G4** Integration: query w/ funded querier → invoice issued → ledger transfer → narrative returned (status='settled') | inbound credit path wired |
| **G5** Integration: query w/ unfunded querier → invoice 'invalidated' + fallback 응답 ("토큰이 부족하시구먼...") | reject UX consistent |
| **G6** Regression: `payment_enabled=false` config로 기존 291 test 전부 PASS | backward compat 명문화 |
| **G7** Simulation: `scripts/credits_sim.py` 5-agent 50-publish + dup-hash spam → ≥1 reject + value-cost 산점도 데이터 | hypothesis §4 measurable |
| **G8** Kill-switch: `OLDMAN_PAYMENT_KILL_SWITCH=true` 설정 시 ledger.transfer noop + log warning + free path 회귀 | demo emergency exit |

**v1.5α ship 조건**: G1-G8 전부 PASS.

**v1.5β ship 조건** (선택, β 진입 시): G7+G8 + (β-Live) Base Sepolia 1건 e2e via `scripts/payment_smoke.sh` + EVAL-2 hallucination rate 재측정 < 1% (re-baseline trigger T7d).

## 10. Open questions (resolved or deferred)

1. ~~Wallet 1개 공용 vs per-agent?~~ — RESOLVED: α는 in-process ledger라 wallet 개념 없음. β는 oldman 1개 hot wallet.
2. ~~Outbound x402가 transaction 안에 들어가도 안전한가?~~ — RESOLVED via D10 (β settle-outside-TX). α는 in-process라 무관.
3. ~~Invoice를 events 테이블에 join할 필요?~~ — RESOLVED: `events.credits_tx_id` + `credits_transactions.invoice_id` chain으로 JOIN 가능. reporting 시점 평가.
4. ~~Per-query pricing?~~ — DEFERRED: α는 flat 1 credit per query. variance metric 본 후 v2.
5. ~~AgentCard 확장?~~ — DEFERRED: β에서 `x-oldman.payment` extension에 `credits` mode flag 노출 검토.
6. **NEW**: Cross-agent simulation script의 spam pattern 디자인 — 운영자가 작성? T-shaped golden set? → α 구현 시 결정. (G7 scope 안.)

## 11. Implementation order

### v1.5α (this PRD, ~2h CC)

1. **Migration 002 + ledger schema** (30min) — credits_balances + credits_transactions + events.credits_tx_id + indexes. **T6 (outside voice)**: T1 verify step에 `cp oldman.duckdb /tmp/migration_test.duckdb && python -m app.storage.db apply_migrations` 추가 — production DB copy migration 검증.
2. **`app/credits/ledger.py`** (40min) — `Ledger.transfer` + `apply_starting_grant` + 5 unit cases. G1 GREEN.
3. **publish.py + executor.py wiring** (30min) — `payment_enabled=true` 시 ledger.transfer 호출 (publish는 TX 안, query는 invoice→ledger→narrative). G2/G3/G4/G5 GREEN.
4. **Config + bootstrap + kill-switch** (15min) — `config/payment.yaml` + `OLDMAN_PAYMENT_KILL_SWITCH` env. G8 GREEN.
5. **Backward compat regression** (15min) — G6.
6. **`scripts/credits_sim.py`** (30min) — 5-agent simulation + spam pattern + 산점도 출력. G7 GREEN.

→ Ship gate: G1-G8 PASS. K1 평가 시작.

### v1.5β (deferred + cancellable PRD addendum, ~5h CC)

α의 K1 통과 후에만 진입.

7. **`app/payment/x402.py`** (1.5h) — Spike A 내부화. ledger.transfer 직전에 real settlement (D10 settle-outside-TX).
8. **executor.py real PaymentMiddlewareASGI integration** (1h) — Spike B 패턴 mirror.
9. **config + wallet env** (30min).
10. **`/admin/memory` ledger + on-chain stats** (30min).
11. **`scripts/payment_smoke.sh`** (30min) — manual Base Sepolia e2e.
12. **EVAL-2 re-baseline** (30min) — `publish.py` + `executor.py` 변경 trigger.
13. **Demo 영상** (30min, optional) — α credits + β cinematic shot.

→ Ship gate: G7 simulation + (β-Live) Base Sepolia 1회 + EVAL-2 PASS.

**Pivot decision point** (between α and β): K1 fired → β archive + DESIGN_NOTES.md 회고. K1 통과 → β 진행. 운영자 직접 cancel 옵션 가짐.

---

## Appendix A — schema (migrations/002_payments.sql draft)

```sql
-- 002: credits ledger for v1.5α 양방향 결제 토폴로지 (off-chain).
-- v1.5β에 real x402 wiring 시 credits_transactions가 mirror 기록 역할.

-- A. balances (cached projection of credits_transactions)
CREATE TABLE IF NOT EXISTS credits_balances (
  agent_id      VARCHAR PRIMARY KEY,
  balance       INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  last_updated  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- B. immutable transaction log (D3)
CREATE TABLE IF NOT EXISTS credits_transactions (
  tx_id         UUID PRIMARY KEY,
  ts            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  from_agent    VARCHAR,         -- NULL = system grant
  to_agent      VARCHAR,         -- NULL = system burn
  amount        INTEGER NOT NULL CHECK (amount > 0),
  reason        VARCHAR NOT NULL CHECK (reason IN (
                  'publish_reward','query_price','starting_grant',
                  'admin_adjust','rejected_insufficient_funds'
                )),
  event_id      UUID,
  invoice_id    UUID,
  outcome       VARCHAR NOT NULL CHECK (outcome IN (
                  'applied','rejected_insufficient_funds','rejected_invalid_agent'
                ))
);
CREATE INDEX IF NOT EXISTS idx_credits_tx_ts
  ON credits_transactions(ts DESC);
CREATE INDEX IF NOT EXISTS idx_credits_tx_from
  ON credits_transactions(from_agent, ts DESC);
CREATE INDEX IF NOT EXISTS idx_credits_tx_to
  ON credits_transactions(to_agent, ts DESC);

-- C. events column for join (D9: append-only invariant preserved — no FK)
ALTER TABLE events ADD COLUMN credits_tx_id UUID;
CREATE INDEX IF NOT EXISTS idx_events_credits_tx ON events(credits_tx_id);

-- D. invoices (Spike B pattern, reused)
CREATE TABLE IF NOT EXISTS invoices (
  invoice_id      UUID PRIMARY KEY,
  query           TEXT NOT NULL,
  subject_agent   VARCHAR,
  intent_expiry   TIMESTAMP NOT NULL,
  status          VARCHAR NOT NULL CHECK (status IN ('pending','settled','expired','invalidated')),
  credits_tx_id   UUID,
  issued_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  settled_at      TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invoices_status_expiry
  ON invoices(status, intent_expiry);
```

## Appendix B — config (config/payment.yaml draft)

```yaml
# v1.5α default — credits-only, fully backward compatible.
enabled: false
mode: credits                  # credits (α) | x402_real (β)

prices:
  publish_reward: 1            # oldman → source_agent on successful publish
  query_price:    1            # querier → oldman on successful narrative
  starting_grant: 100          # lazy-applied on first publish/query per agent

# β-only (mode=x402_real)
wallet:
  key_env: EVM_PRIVATE_KEY
  receive_address_env: EVM_RECEIVE_ADDRESS
network: eip155:84532
asset:   "0x036CbD53842c5426634e7929541eC2318f3dCF7e"   # USDC Base Sepolia
facilitator_url: https://x402.org/facilitator
credit_to_usdc_ratio: 0.001    # 1 credit = 0.001 USDC

# common
invoice_ttl_seconds: 300
cleanup_interval_seconds: 60

# emergency exit (D8 / outside voice T7c)
# kill_switch_env: OLDMAN_PAYMENT_KILL_SWITCH
```

## Appendix C — links

- `~/.gstack/projects/oldman_agent/qkdwodus777-unknown-design-20260518-231759.md` — original design doc
- `.claude/prds/oldman-agent-v1.prd.md` — v1 baseline (memory + persona)
- `.claude/prds/oldman-agent-v2.prd.md` — v2 (A2A v0.3 messaging compliance)
- `spikes/spike_a_outcome.md` — outbound x402 verified to boundary (β reference)
- `spikes/spike_b_outcome.md` — inbound ap2+x402 verified to boundary (β reference)
- `eval/baselines/v2.5_live_baseline.md` — current EVAL state

---

## Eng-review findings — applied + post-outside-voice (2026-05-31)

Scope: prior /plan-eng-review (mock x402 α/β) → outside voice critique → **credits pivot**. PRD rewritten. Findings status:

### From original eng review (still relevant after pivot)
- **A1 events payment invariant** — REPLACED: `credits_balances.balance >= 0` CHECK + `events.credits_tx_id` nullable (no FK to preserve append-only). Equivalent schema-layer enforcement.
- **A2 invoices FK** — APPLIED: `invoices.credits_tx_id` nullable; events.credits_tx_id nullable. JOIN at reporting time.
- **A3 outbound payment in TX** — MOOT for α (in-process synchronous), HANDLED for β via D10 (settle-outside-TX).
- **A4 background invoice cleanup** — APPLIED unchanged from prior PRD.
- **C1 PaymentClient Protocol** — DROPPED for α (over-abstraction per D2). Lives in β only.
- **C2 ASCII pipeline diagrams** — APPLIED to `app/credits/ledger.py` + `app/api/publish.py` modification.

### From outside voice (2026-05-31)
- **T1 Strategic premise (premise is narrative not architectural)** — ACCEPTED. PRD §1 + §4 rewritten as "narrative differentiator with measurable proxy via credits sim."
- **T2 K1 circular** — RESOLVED via new K1: α-only simulation can fire K1 (spam suppression + value-differential observations).
- **T3 Mock tests boring half** — RESOLVED by removing mock entirely. α tests the actual ledger, β tests the actual chain.
- **T4 Off-ledger credits alternative** — ACCEPTED as α. PRD pivoted.
- **T5 A3 deferred defect (mock 0-latency hides real-client TX block)** — HANDLED via D10 settle-outside-TX in β.
- **T6 T1 migration verify on prod copy** — APPLIED: §11 Step 1 verify step now includes `cp prod.duckdb test_migration.duckdb && apply_migrations`.
- **T7a Outbound x402 idempotency** — APPLIED via D9 (reuse `payload_hash` UNIQUE as idempotency key in β).
- **T7b Invoice cleanup RETURNING** — APPLIED: cleanup task uses `UPDATE ... WHERE status='pending' AND intent_expiry < NOW() RETURNING invoice_id` for race-safe ownership.
- **T7c Kill-switch env** — APPLIED via D8: `OLDMAN_PAYMENT_KILL_SWITCH` + G8 test.
- **T7d EVAL re-baseline trigger** — APPLIED: `CLAUDE.md` "Prompt/LLM changes" 트리거 리스트에 `publish.py` + `executor.py` 추가 필요. β ship gate에 EVAL-2 재측정 포함.
- **T8 Protocol durability** — ACKNOWLEDGED. β cancellable; demo-only scope. v2에서 다른 ledger 백엔드 고려.

### Implementation Tasks (synthesized)

- [ ] **T1 (P1, human: ~30min / CC: ~5min)** — schema — migration 002 ledger + invoices + events.credits_tx_id + CHECK constraints. **Verify**: prod DB copy migration + 기존 291 tests still PASS.
- [ ] **T2 (P1, human: ~40min / CC: ~10min)** — credits — `app/credits/ledger.py` + 5 unit cases incl. v2.5 T4 regression.
- [ ] **T3 (P1, human: ~30min / CC: ~10min)** — wiring — publish.py + executor.py ledger calls. G2-G5.
- [ ] **T4 (P1, human: ~15min / CC: ~5min)** — config — `config/payment.yaml` + kill-switch env. G8.
- [ ] **T5 (P2, human: ~15min / CC: ~5min)** — regression — `payment_enabled=false` G6.
- [ ] **T6 (P1, human: ~30min / CC: ~10min)** — simulation — `scripts/credits_sim.py` 5-agent 50-publish + 산점도. G7 — **hypothesis test**.
- [ ] **T7 (P2, human: ~10min / CC: ~5min)** — docs — CLAUDE.md EVAL trigger list에 `publish.py` + `executor.py` 추가. ASCII diagram in `app/credits/ledger.py`.

Total v1.5α: ~2h CC, ~2.5h human.

### Unresolved decisions

(none — all outside voice findings resolved or explicitly deferred to β cancellable)

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | scope α/β split → credits pivot post-outside-voice; all findings APPLIED or DEFERRED to cancellable β |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE VOICE:** Claude subagent ran (Codex unavailable). 8 findings: T4 credits alternative ACCEPTED → PRD pivoted; T1+T2+T3 resolved by pivot; T5+T6+T7a-d all APPLIED inline.
- **CROSS-MODEL:** Outside voice + eng review agree on schema-layer invariant enforcement + race-safety pattern reuse from v2.5. No remaining tension.
- **UNRESOLVED:** 0
- **VERDICT:** ENG CLEARED (PLAN, post-outside-voice pivot) — v1.5α ready to implement (~2h CC). v1.5β cancellable, conditional on α K1 outcome.
