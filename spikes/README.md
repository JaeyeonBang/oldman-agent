# Spike A — Outbound x402 Payment

Verifies one successful pay-to-share cycle: 꼰대(client) pays 0.001 USDC on Base Sepolia
to the publisher server, receives JSON confirming receipt.

## Run

**1. Install**
```bash
cd spikes/
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**2. Generate wallet**
```bash
python3 -c "from eth_account import Account; a=Account.create(); print('KEY=', a.key.hex()); print('ADDR=', a.address)"
# Copy both values into .env (see .env.example)
```

**3. Fund faucets (Base Sepolia)**
- ETH (gas): https://www.alchemy.com/faucets/base-sepolia
- USDC:       https://faucet.circle.com (no signup needed)

**4. Start server** (terminal 1)
```bash
cp .env.example .env  # fill in EVM_RECEIVE_ADDRESS
export $(cat .env | grep -v '#' | xargs)
python publisher_server.py
```

**5. Run client** (terminal 2)
```bash
export $(cat .env | grep -v '#' | xargs)
python outbound_x402.py
```

## Success output
```
[OK] status=200 path=/publish-info tx=<tx_hash> amount=<amount> asset=USDC
[BODY] {"received": true, "echo": {...}}
[PAYMENT-RESPONSE] <full header>
```

**Note**: buyer and seller can share the same wallet for spike purposes (self-payment); only Base Sepolia gas is consumed. For production use separate wallets.

**Pivot trigger**: If blocked >1 day on x402/ap2 SDK issues → see `TODOS.md` pivot section (cinematic mock mode).
