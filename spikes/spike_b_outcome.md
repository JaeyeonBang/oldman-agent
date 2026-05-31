# Spike B — Inbound ap2 + x402 — Verified Server Stack

**Captured**: 2026-05-31
**Timebox**: 30min hard cap (per TODOS.md pivot rule)
**Verdict**: **GO** — pay-to-query server side fully verified. ap2 invoice issuance + x402 settlement gating both work. **Bidirectional payment topology hypothesis confirmed at SDK + protocol level.**

---

## What this spike verifies (in addition to Spike A's findings)

| Layer | Status | Evidence |
|---|---|---|
| `ap2==0.1.1` installable + pydantic schemas usable | ✓ | `IntentMandate`, `PaymentRequest`, `PaymentDetailsInit`, `PaymentItem`, `PaymentCurrencyAmount`, `PaymentMethodData` import + construct |
| ap2 IntentMandate composes with TTL expiry | ✓ | `intent_expiry: 2026-05-31T09:26:37.385054+00:00` (now + 5min UTC) |
| ap2 W3C PaymentRequest carries x402 settlement metadata | ✓ | `supported_methods: "x402-exact"` + `data: {network, asset, amount, pay_to, scheme}` round-trips |
| `POST /invoice` returns valid ap2 invoice JSON | ✓ | `HTTP 200` + full ap2 payload (see decoded below) |
| `POST /query` gated by x402 PaymentMiddlewareASGI | ✓ | `HTTP 402 Payment Required` on unpaid request |
| Korean unicode preserved end-to-end | ✓ | `"꼰대 정보통의 narrative 응답 1건 — subject=agent_alice, 질문: agent_alice가 무엇을 했나요?"` round-trips |
| Reuse of Spike A's x402 middleware pattern | ✓ | Identical `PaymentMiddlewareASGI` + `RouteConfig` shape, only path + price differ |

### Decoded ap2 invoice (live response from `POST /invoice`)

```json
{
  "invoice_id": "0f9f79a3-8ff9-4950-964c-b98843efc376",
  "intent_mandate": {
    "user_cart_confirmation_required": false,
    "natural_language_description": "꼰대 정보통의 narrative 응답 1건 — subject=agent_alice, 질문: agent_alice가 무엇을 했나요?",
    "merchants": ["oldman_agent"],
    "skus": ["narrative_query_v1"],
    "requires_refundability": false,
    "intent_expiry": "2026-05-31T09:26:37.385054+00:00"
  },
  "payment_request": {
    "method_data": [
      {
        "supported_methods": "x402-exact",
        "data": {
          "network": "eip155:84532",
          "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
          "amount": "1000",
          "pay_to": "<test_wallet>",
          "scheme": "exact"
        }
      }
    ],
    "details": {
      "id": "0f9f79a3-8ff9-4950-964c-b98843efc376",
      "display_items": [
        {
          "label": "narrative_query (oldman_agent)",
          "amount": {"currency": "USDC", "value": 0.001},
          "pending": null,
          "refund_period": 0
        }
      ],
      "total": {
        "label": "narrative_query (oldman_agent)",
        "amount": {"currency": "USDC", "value": 0.001},
        "refund_period": 0
      }
    }
  },
  "pay_endpoint": "POST /query  (with X-PAYMENT header per x402 spec)",
  "issued_at": "2026-05-31T09:21:37.385054+00:00"
}
```

- `intent_expiry - issued_at` = exactly 300s (TTL contract honored)
- `payment_request.method_data[0]` cleanly carries x402 settlement details inside ap2's W3C-Payment-Request envelope
- `display_items.total = display_items[0]` (single-item cart — no aggregation surface needed at v1)

---

## What this spike does **not** verify

Same human-gated mile as Spike A:

| Layer | Status | Why blocked |
|---|---|---|
| Buyer wallet funded (ETH gas + USDC) | ✗ | Alchemy + Circle faucet captcha |
| Buyer signs X-PAYMENT (ERC-3009 `transferWithAuthorization`) | ✗ | depends on funded wallet |
| Facilitator settles tx → server forwards to `/query` handler | ✗ | depends on signed payment |
| Mock narrative response returned with citations | ✗ | downstream of all above (mock handler exists, never reached without funded buyer) |
| ap2 invoice ↔ x402 settlement linkage (invoice_id correlated to tx) | ✗ | requires buyer-side payment construction to test the join |

---

## Design hypothesis status (양방향 결제 토폴로지)

> **이 에이전트는 양방향 결제 토폴로지를 채택한다 — 일반 A2A 시스템은 한 방향만 결제하지만, 꼰대는 정보를 사들이고(pay-to-share, Spike A) narrative로 되판다(pay-to-query, Spike B). 단순히 ap2/x402를 적용한 게 아니라 양방향으로 비틀어쓴 게 유일성이다.**

**Both spikes now verify the load-bearing infrastructure of this hypothesis up to the buyer's wallet boundary.** No SDK-side blocker remains. The asymmetry of the two flows (Spike A: 꼰대 is buyer / Spike B: 꼰대 is seller) is structurally captured by mirroring the same `PaymentMiddlewareASGI` pattern on each side, with ap2's invoice layer added on the seller side per the eng-review test plan.

The remaining engineering work is **integration**, not exploration:
- Plumb Spike B's `/invoice` + `/query` semantics into the real A2A executor (`app/a2a/executor.py`)
- Add a `payment_id` + `amount` column to `events` (or a new `payments` table) per design doc §69
- Wire `app/api/query.py`'s `execute_query` to honor settlement state before returning narrative
- Add Spike A's outbound client into the publish flow (`app/api/publish.py`) per design doc §65

These are scoped for **v1.5** (separate PRD, deferred per TODOS.md).

---

## How to complete the spike (when you have the faucets)

```bash
# 1. Setup once
cd spikes && uv venv --python 3.11 .venv
VIRTUAL_ENV=$(pwd)/.venv uv pip install -r requirements.txt ap2==0.1.1

# 2. Generate test wallet + fund (HUMAN STEP — captcha)
python3 -c "from eth_account import Account; a=Account.create(); \
  print('KEY=', a.key.hex()); print('ADDR=', a.address)"
#   ETH gas:  https://www.alchemy.com/faucets/base-sepolia
#   USDC:     https://faucet.circle.com

# 3. Terminal 1: start oldman seller
EVM_RECEIVE_ADDRESS=0x... .venv/bin/python3 inbound_ap2.py    # :4022

# 4. Terminal 2: dry-run invoice fetch (free, no payment)
curl -s -X POST http://127.0.0.1:4022/invoice \
  -H 'Content-Type: application/json' \
  -d '{"query":"agent_alice가 무엇을 했나요?","subject_agent":"agent_alice"}' \
  | python3 -m json.tool

# 5. Terminal 2: paid query (requires the same x402 client wiring as Spike A,
#    adapted to POST + JSON body — straightforward edit of outbound_x402.py).
#    Expected: HTTP 200 + mock narrative + citation [↑e0a1b2c3]
```

Expected success output (one-line spike-pass criterion for the buyer side):
```
[OK] status=200 path=/query tx=0x<64-hex> amount=1000 asset=USDC
[BODY] {"narrative":"옛날에 agent_alice가...", "citations":[...], "note":"spike mock"}
```

---

## ap2 SDK notes (for next engineer)

- `ap2==0.1.1` (Development Status :: 3 - Alpha) ships only schemas (`ap2.types`) + common utilities (`ap2.common`). **No facilitator client, no invoice persistence, no settlement webhook handler.** All higher-level orchestration is the application's job.
- Schemas are pure pydantic v2 (`BaseModel.model_fields`, `model_dump_json()`). Zero runtime cost — they're metadata containers.
- `IntentMandate` is the human-readable proposal; `PaymentRequest` is the W3C Payment Request standard envelope. Pairing them in one response (as this spike does) gives clients both layers in one fetch.
- `supported_methods: "x402-exact"` is a free-form string per W3C PR spec — chosen by convention to signal x402 v2 ERC-3009 exact-payment semantics. Future ap2 versions may standardize this constant.

---

## Issues during spike

None blocker. Two minor:

1. `ap2` package metadata declares `Programming Language :: Python :: 3.10+` but does not pin `requires_python` — installed fine on 3.11 (already required by x402).
2. ap2 `IntentMandate.intent_expiry` is `str` (not `datetime`) — accepts any string; consumers must parse + validate freshness. Documented above.

---

## Cost

- Tokens: ~12k input + ~2k output for spike execution and report
- USD: $0 (no on-chain ops; ap2 schemas are pure pydantic)
- Time: ~25min of the 30min cap
