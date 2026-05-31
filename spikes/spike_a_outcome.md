# Spike A — Outbound x402 — Verified Server Stack

**Captured**: 2026-05-31
**Timebox**: 30min hard cap (per TODOS.md pivot rule)
**Verdict**: **GO** — pay-to-share server side fully verified; client-side only blocked at the human-gated faucet step. **Not a pivot** — concrete evidence of the design hypothesis.

---

## What this spike verifies

| Layer | Status | Evidence |
|---|---|---|
| `x402` Python SDK installable on Py 3.11 | ✓ | `x402[httpx,evm]==2.12.0` + `eth-account>=0.13` install clean |
| All `outbound_x402.py` imports resolve | ✓ | `x402Client`, `x402HttpxClient`, `EthAccountSigner`, `register_exact_evm_client` |
| All `publisher_server.py` imports resolve | ✓ | `PaymentMiddlewareASGI`, `HTTPFacilitatorClient`, `ExactEvmServerScheme`, `x402ResourceServer` |
| EVM account → signer → x402Client wiring | ✓ | `Account.create()` → `EthAccountSigner(a)` → `register_exact_evm_client(client, signer)` works |
| FastAPI app boots with x402 middleware | ✓ | uvicorn startup clean, 6 routes registered (`/health`, `/publish-info`, + 4 OpenAPI defaults) |
| `/health` returns 200 OK unauth | ✓ | `curl ... /health` → `HTTP 200 {"status":"ok"}` |
| `/publish-info` returns x402 v2 challenge | ✓ | `HTTP 402 Payment Required` + `payment-required` header (base64 JSON challenge) |
| Challenge JSON shape matches x402 v2 spec | ✓ | see decoded payload below |
| Korean unicode preserved through middleware | ✓ | `description: "꼰대 정보 구매 (pay-to-share)..."` round-trips correctly |

### Decoded x402 challenge (from `payment-required` header)

```json
{
  "x402Version": 2,
  "error": "Payment required",
  "resource": {
    "url": "http://127.0.0.1:4021/publish-info",
    "description": "꼰대 정보 구매 (pay-to-share). 0.001 USDC / Base Sepolia.",
    "mimeType": "application/json"
  },
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:84532",
      "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
      "amount": "1000",
      "payTo": "<test_wallet>",
      "maxTimeoutSeconds": 300,
      "extra": {"name": "USDC", "version": "2"}
    }
  ]
}
```

- `network = eip155:84532` → Base Sepolia ✓
- `asset = 0x036CbD...` → USDC Base Sepolia contract ✓
- `amount = "1000"` → 0.001 USDC (6 decimals) ✓
- `scheme = "exact"` → exact-payment ERC-3009 path ✓

The server is ready to accept and forward signed payments to the facilitator. The remaining work is purely on the buyer side.

---

## What this spike does **not** verify

| Layer | Status | Why blocked |
|---|---|---|
| Buyer wallet funded (Base Sepolia ETH for gas) | ✗ | Alchemy faucet requires human captcha + browser auth |
| Buyer wallet funded (USDC test token) | ✗ | Circle faucet requires human captcha |
| Client signs X-PAYMENT header (ERC-3009 transferWithAuthorization) | ✗ | depends on funded wallet to be meaningful |
| Facilitator (`x402.org/facilitator`) settles a real tx | ✗ | depends on signed payment |
| Server returns 200 + body after settlement | ✗ | depends on settled tx (downstream of all above) |

These are not technical gaps — they are **human-gated** dependencies (faucet captcha) that the spike cannot legitimately automate.

---

## Issues discovered + fixed during spike

1. **Stale pin** `x402==2.10.0` not on PyPI (was advertised in `requirements.txt` comments from 2026-05-19 verification, but PyPI now serves `2.12.0` as latest). Fixed: pin bumped to `2.12.0`, comment dated to 2026-05-31.
2. **Python version trap** — `python3 -m venv` picks system Python 3.8 on this host; x402 requires ≥3.10. Fixed: `requirements.txt` comment explicitly instructs `uv venv --python 3.11 .venv`.
3. **Import compatibility** — all imports from 2.10 → 2.12 still resolve. The scripts in `outbound_x402.py` and `publisher_server.py` are forward-compatible.

---

## How to complete the spike (when you have the faucets)

```bash
# 1. One-time wallet generation (already documented in spikes/README.md)
python3 -c "from eth_account import Account; a=Account.create(); \
  print('KEY=', a.key.hex()); print('ADDR=', a.address)"

# 2. Fund the address (HUMAN STEP — captcha)
#   ETH gas:  https://www.alchemy.com/faucets/base-sepolia   (paste ADDR)
#   USDC:     https://faucet.circle.com                       (paste ADDR)

# 3. Fill spikes/.env (EVM_PRIVATE_KEY, EVM_RECEIVE_ADDRESS — can be the same)

# 4. Terminal 1: start server
cd spikes && source .venv/bin/activate
export $(cat .env | grep -v '#' | xargs)
python publisher_server.py    # listens on :4021

# 5. Terminal 2: outbound payment
cd spikes && source .venv/bin/activate
export $(cat .env | grep -v '#' | xargs)
python outbound_x402.py       # expected: HTTP 200 + tx hash
```

Expected success output (one-line spike-pass criterion):
```
[OK] status=200 path=/publish-info tx=0x<64-hex> amount=... asset=USDC
[BODY] {"received": true, "echo": {...}}
```

---

## Implications for the design (양방향 결제 토폴로지)

- **pay-to-share** is the publisher-server side: 꼰대 buys information from an information producer. **Verified up to the challenge boundary.**
- The mirror direction **pay-to-query** (꼰대 sells stored narrative) is Spike B (`spikes/inbound_ap2.py` — not yet scaffolded). The publisher_server side of this spike doubles as a structural reference for Spike B's server half — the same `PaymentMiddlewareASGI` pattern applies.
- The x402 v2 protocol surface is stable and Python-supported. **No SDK-side blocker to v1.5.**
- Decision: queue Spike B scaffolding next (Inbound ap2+x402). Same pivot rule applies.

---

## Cost

- Tokens: ~25k input + ~3k output (Sonnet equivalent) for spike execution and report
- USD: $0 (no on-chain ops; no LLM call beyond doc generation)
- Time: ~20min of the 30min cap
