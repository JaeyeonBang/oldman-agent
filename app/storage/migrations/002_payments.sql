-- 002: credits ledger for v1.5α 양방향 결제 토폴로지 (off-chain).
-- v1.5β에서 real x402 wiring 시 credits_transactions가 mirror 기록 역할.
--
-- Safe on populated tables: all new tables are independent of `events`.
-- The ALTER on `events` adds a nullable column — DuckDB validates CHECK
-- constraints on existing rows, but `credits_tx_id IS NULL` for legacy
-- rows always satisfies the (implicit nullable) contract.

-- A. balances (cached projection of credits_transactions; can be
--    rebuilt from the transaction log if it ever drifts).
CREATE TABLE IF NOT EXISTS credits_balances (
  agent_id      VARCHAR PRIMARY KEY,
  balance       INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  last_updated  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- B. immutable transaction log (PRD D3 — append-only audit trail).
CREATE TABLE IF NOT EXISTS credits_transactions (
  tx_id         UUID PRIMARY KEY,
  ts            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  from_agent    VARCHAR,
  to_agent      VARCHAR,
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

-- C. join column on events (PRD D9 — append-only invariant preserved by
--    NOT enforcing FK; reporting JOIN via this col).
ALTER TABLE events ADD COLUMN credits_tx_id UUID;
CREATE INDEX IF NOT EXISTS idx_events_credits_tx ON events(credits_tx_id);

-- D. invoices (Spike B pattern, reused for pay-to-query lifecycle).
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
