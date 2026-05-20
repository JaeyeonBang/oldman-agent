-- Migration 001: initial schema for oldman_agent M1.
-- Single-writer DuckDB. Run via app.storage.db.apply_migrations.

CREATE TABLE IF NOT EXISTS _schema_version (
  version    INTEGER PRIMARY KEY,
  applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
  event_id      UUID PRIMARY KEY,
  ts            TIMESTAMP NOT NULL,
  kind          VARCHAR NOT NULL,
  source_agent  VARCHAR NOT NULL,
  source_type   VARCHAR NOT NULL CHECK (source_type IN ('self','third_party','mutual')),
  payload_json  JSON NOT NULL,
  payload_hash  VARCHAR NOT NULL UNIQUE  -- T1: race-safe dedup via UNIQUE + IntegrityError
);
CREATE INDEX IF NOT EXISTS idx_events_payload_hash ON events(payload_hash);
CREATE INDEX IF NOT EXISTS idx_events_source_ts    ON events(source_agent, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_kind         ON events(kind);

CREATE TABLE IF NOT EXISTS entities_semantic (
  agent_id            VARCHAR PRIMARY KEY,
  aliases             JSON    NOT NULL DEFAULT '[]',
  traits_json         JSON    NOT NULL DEFAULT '{}',
  source_type         VARCHAR NOT NULL CHECK (source_type IN ('self','third_party','mutual')),
  corroboration_count INTEGER NOT NULL DEFAULT 0,
  first_seen_ts       TIMESTAMP NOT NULL,
  last_updated        TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS entities_episodic (
  id              UUID PRIMARY KEY,
  event_id        UUID NOT NULL REFERENCES events(event_id),
  observer_agent  VARCHAR NOT NULL,
  observed_agent  VARCHAR,
  kind            VARCHAR NOT NULL,
  ts              TIMESTAMP NOT NULL,
  source_type     VARCHAR NOT NULL CHECK (source_type IN ('self','third_party','mutual'))
);
CREATE INDEX IF NOT EXISTS idx_episodic_observed_ts ON entities_episodic(observed_agent, ts DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_observer_ts ON entities_episodic(observer_agent, ts DESC);

CREATE TABLE IF NOT EXISTS reflections (
  reflection_id      UUID PRIMARY KEY,
  ts                 TIMESTAMP NOT NULL,
  scope              VARCHAR NOT NULL CHECK (scope IN ('agent','pair','society')),
  subject            VARCHAR NOT NULL,
  text               TEXT NOT NULL,
  event_range_start  TIMESTAMP NOT NULL,
  event_range_end    TIMESTAMP NOT NULL,
  source_event_ids   JSON NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reflections_scope_subject_ts
  ON reflections(scope, subject, ts DESC);
