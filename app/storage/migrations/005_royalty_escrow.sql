-- Migration 005: P2 royalty escrow — 매입 대금의 deferred 지급분 회계.
-- open: 인용 대기 / paid: 유료 query 인용으로 지급 / expired: horizon 경과 소멸.

CREATE TABLE IF NOT EXISTS royalty_escrows (
  event_id     VARCHAR PRIMARY KEY,   -- events.event_id (판매된 정보)
  seller_agent VARCHAR NOT NULL,
  amount       INTEGER NOT NULL,
  created_ts   TIMESTAMP NOT NULL,
  expires_ts   TIMESTAMP NOT NULL,
  status       VARCHAR NOT NULL DEFAULT 'open'
               CHECK (status IN ('open','paid','expired')),
  paid_tx_id   VARCHAR,
  paid_ts      TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_royalty_escrows_status ON royalty_escrows(status, expires_ts);
