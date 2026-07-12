-- Migration 004: P1 trust ledger — 마을 명부 + Beta 점수 + 신뢰 이벤트.
-- 모든 점수 갱신은 trust_events에 원인 ref와 함께 기록된다 ("점수의 citation").

CREATE TABLE IF NOT EXISTS village_registry (
  agent_id         VARCHAR PRIMARY KEY,  -- == events.source_agent
  state            VARCHAR NOT NULL CHECK (
                     state IN ('provisional','member','warned','penalized','excluded')
                   ),
  violation_count  INTEGER NOT NULL DEFAULT 0,
  joined_at        TIMESTAMP NOT NULL,
  state_changed_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS trust_ledger (
  agent_id       VARCHAR NOT NULL,
  criterion      VARCHAR NOT NULL CHECK (criterion IN ('reliability','honesty')),
  alpha          DOUBLE NOT NULL,
  beta           DOUBLE NOT NULL,
  last_update_ts TIMESTAMP NOT NULL,
  PRIMARY KEY (agent_id, criterion)
);

CREATE TABLE IF NOT EXISTS trust_events (
  trust_event_id UUID PRIMARY KEY,
  ts             TIMESTAMP NOT NULL,
  agent_id       VARCHAR NOT NULL,
  criterion      VARCHAR NOT NULL,
  positive       BOOLEAN NOT NULL,
  weight         DOUBLE NOT NULL,
  cause          VARCHAR NOT NULL,   -- e.g. 'publish_settled', 'canary_fail', 'grounding_contradiction'
  cause_ref      VARCHAR             -- event_id / tx_id 등 원인 참조
);
CREATE INDEX IF NOT EXISTS idx_trust_events_agent_ts ON trust_events(agent_id, ts DESC);
