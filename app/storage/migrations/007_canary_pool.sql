-- Migration 007: P3 canary pool — 정직성 감사용 심어둔 사실 (1회용, 회전).

CREATE TABLE IF NOT EXISTS canary_pool (
  canary_id    UUID PRIMARY KEY,
  planted_ts   TIMESTAMP NOT NULL,
  topic        VARCHAR NOT NULL,
  answer_key   JSON NOT NULL,        -- 심어둔 사실 (되사기 대조 기준)
  used         BOOLEAN NOT NULL DEFAULT FALSE,
  used_ts      TIMESTAMP,
  target_agent VARCHAR               -- 특정 판매자 겨냥 시 (선택)
);
CREATE INDEX IF NOT EXISTS idx_canary_pool_unused ON canary_pool(used, topic);
