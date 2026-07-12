"""``agent_identities`` 저장 — network-local agent ↔ DID ↔ ERC-8004 agentId 매핑.

publish 경로의 seller_did와 함께 P0 provenance의 저장 반쪽. 트랜잭션은
호출자가 관리하지 않아도 되는 단건 upsert/조회 (publish TX 밖에서 사용).
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb


@dataclass(frozen=True)
class AgentIdentityRow:
    agent_id: str
    did: str
    erc8004_agent_id: int | None
    erc8004_chain: str | None


def upsert_agent_identity(
    conn: duckdb.DuckDBPyConnection,
    *,
    agent_id: str,
    did: str,
    erc8004_agent_id: int | None = None,
    erc8004_chain: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO agent_identities "
        "(agent_id, did, erc8004_agent_id, erc8004_chain) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (agent_id) DO UPDATE SET "
        "did = excluded.did, "
        "erc8004_agent_id = excluded.erc8004_agent_id, "
        "erc8004_chain = excluded.erc8004_chain",
        [agent_id, did, erc8004_agent_id, erc8004_chain],
    )


def get_agent_identity(
    conn: duckdb.DuckDBPyConnection, agent_id: str
) -> AgentIdentityRow | None:
    row = conn.execute(
        "SELECT agent_id, did, erc8004_agent_id, erc8004_chain "
        "FROM agent_identities WHERE agent_id = ?",
        [agent_id],
    ).fetchone()
    if row is None:
        return None
    return AgentIdentityRow(
        agent_id=row[0],
        did=row[1],
        erc8004_agent_id=row[2],
        erc8004_chain=row[3],
    )
