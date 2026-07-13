-- Migration 009: credits_transactions from/to 인덱스 복구 (M5).
-- 002가 만든 idx_credits_tx_from/to는 006·008의 테이블 재생성(DROP+RENAME)에서
-- 사라지고 재생성되지 않았다 — from_agent로 GROUP/필터하는 감사·admin 쿼리가
-- full scan이 되므로 여기서 복구한다. (idx_credits_tx_ts는 006/008이 유지.)

CREATE INDEX IF NOT EXISTS idx_credits_tx_from
  ON credits_transactions(from_agent, ts DESC);
CREATE INDEX IF NOT EXISTS idx_credits_tx_to
  ON credits_transactions(to_agent, ts DESC);
