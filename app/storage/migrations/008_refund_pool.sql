-- Migration 008: P4 환불 풀 — claim 테이블 + credits reason enum 확장.
-- 'pool_fee'(정산 query당 풀 적립) + 'refund_payout'(승인 claim 배상) 추가.
-- DuckDB CHECK 변경 불가 → 테이블 재생성 (006과 동일 패턴).

CREATE TABLE IF NOT EXISTS refund_claims (
  claim_id       UUID PRIMARY KEY,
  invoice_id     UUID NOT NULL,
  claimant_agent VARCHAR NOT NULL,
  reason_text    VARCHAR NOT NULL,
  status         VARCHAR NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','approved','denied')),
  filed_ts       TIMESTAMP NOT NULL,
  decided_ts     TIMESTAMP,
  payout_tx_id   VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_refund_claims_status ON refund_claims(status, filed_ts);

CREATE TABLE credits_transactions_v3 (
  tx_id         UUID PRIMARY KEY,
  ts            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  from_agent    VARCHAR,
  to_agent      VARCHAR,
  amount        INTEGER NOT NULL CHECK (amount > 0),
  reason        VARCHAR NOT NULL CHECK (reason IN (
                  'publish_reward','query_price','starting_grant',
                  'admin_adjust','rejected_insufficient_funds',
                  'listing_fee','royalty','pool_fee','refund_payout'
                )),
  event_id      UUID,
  invoice_id    UUID,
  outcome       VARCHAR NOT NULL CHECK (outcome IN (
                  'applied','rejected_insufficient_funds','rejected_invalid_agent'
                ))
);

INSERT INTO credits_transactions_v3 SELECT * FROM credits_transactions;
DROP TABLE credits_transactions;
ALTER TABLE credits_transactions_v3 RENAME TO credits_transactions;

CREATE INDEX IF NOT EXISTS idx_credits_tx_ts
  ON credits_transactions(ts DESC);
