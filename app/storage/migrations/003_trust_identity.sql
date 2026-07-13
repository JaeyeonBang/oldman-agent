-- Migration 003: P0 trust identity — seller DID provenance + ERC-8004 매핑.
-- events.seller_did: 서명 publish의 판매자 did:key. 무서명 legacy publish는 NULL.

ALTER TABLE events ADD COLUMN seller_did VARCHAR;

CREATE TABLE IF NOT EXISTS agent_identities (
  agent_id         VARCHAR PRIMARY KEY,  -- == events.source_agent (network-local name)
  did              VARCHAR NOT NULL UNIQUE,
  erc8004_agent_id BIGINT,               -- ERC-8004 Identity Registry agentId (mock/testnet)
  erc8004_chain    VARCHAR,              -- e.g. 'mock:local', 'eip155:97' (BNB testnet)
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
