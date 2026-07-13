-- Migration 006: credits reason enum 확장 — v2 P2 층위 결제.
-- 'listing_fee'(매입 즉시 지급분) + 'royalty'(인용 시 escrow 해제) 추가.
-- DuckDB는 CHECK 제약 변경이 불가 → 테이블 재생성 + 데이터 보존.

CREATE TABLE credits_transactions_v2 (
  tx_id         UUID PRIMARY KEY,
  ts            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  from_agent    VARCHAR,
  to_agent      VARCHAR,
  amount        INTEGER NOT NULL CHECK (amount > 0),
  reason        VARCHAR NOT NULL CHECK (reason IN (
                  'publish_reward','query_price','starting_grant',
                  'admin_adjust','rejected_insufficient_funds',
                  'listing_fee','royalty'
                )),
  event_id      UUID,
  invoice_id    UUID,
  outcome       VARCHAR NOT NULL CHECK (outcome IN (
                  'applied','rejected_insufficient_funds','rejected_invalid_agent'
                ))
);

INSERT INTO credits_transactions_v2 SELECT * FROM credits_transactions;
DROP TABLE credits_transactions;
ALTER TABLE credits_transactions_v2 RENAME TO credits_transactions;

CREATE INDEX IF NOT EXISTS idx_credits_tx_ts
  ON credits_transactions(ts DESC);
