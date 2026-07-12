"""P0 ERC-8004 Identity Registry — mock 클라이언트 + agent_identities 저장 (TDD).

produce-only 원칙: 등록 파일 발행만. 타인 온체인 평판 소비 없음.
mock이 기본 (OLDMAN_ERC8004_MODE=mock) — testnet 실등록은 후속 스크립트.
"""

from __future__ import annotations

import duckdb

from app.storage.identities import get_agent_identity, upsert_agent_identity
from app.trust.erc8004 import MockERC8004IdentityRegistry
from app.trust.identity import generate_identity


def _registry() -> MockERC8004IdentityRegistry:
    return MockERC8004IdentityRegistry(chain="mock:local")


def test_register_assigns_sequential_agent_ids() -> None:
    reg = _registry()
    a = reg.register(
        agent_domain="kimbot.example", did="did:key:z6MkA", a2a_endpoint="https://kimbot.example"
    )
    b = reg.register(
        agent_domain="leebot.example", did="did:key:z6MkB", a2a_endpoint="https://leebot.example"
    )
    assert a.agent_id == 1
    assert b.agent_id == 2


def test_register_is_idempotent_by_domain() -> None:
    reg = _registry()
    first = reg.register(
        agent_domain="kimbot.example", did="did:key:z6MkA", a2a_endpoint="https://kimbot.example"
    )
    again = reg.register(
        agent_domain="kimbot.example", did="did:key:z6MkA", a2a_endpoint="https://kimbot.example"
    )
    assert again.agent_id == first.agent_id


def test_registration_file_shape_follows_eip8004() -> None:
    """등록 파일: A2A endpoint + DID 상호 참조 (EIP-8004 registration file 형태)."""
    reg = _registry()
    r = reg.register(
        agent_domain="kimbot.example", did="did:key:z6MkA", a2a_endpoint="https://kimbot.example"
    )
    file = r.registration_file
    assert file["name"] == "kimbot.example"
    assert file["did"] == "did:key:z6MkA"
    endpoints = {e["name"]: e for e in file["endpoints"]}
    assert endpoints["A2A"]["endpoint"].startswith("https://kimbot.example")


def test_get_returns_registration() -> None:
    reg = _registry()
    r = reg.register(
        agent_domain="kimbot.example", did="did:key:z6MkA", a2a_endpoint="https://kimbot.example"
    )
    assert reg.get(r.agent_id) == r
    assert reg.get(999) is None


def test_agent_identities_upsert_and_get(tmp_db: duckdb.DuckDBPyConnection) -> None:
    ident = generate_identity()
    upsert_agent_identity(
        tmp_db,
        agent_id="kimbot",
        did=ident.did,
        erc8004_agent_id=7,
        erc8004_chain="mock:local",
    )
    row = get_agent_identity(tmp_db, "kimbot")
    assert row is not None
    assert row.did == ident.did
    assert row.erc8004_agent_id == 7

    # upsert 갱신 — 같은 agent_id 재등록 시 최신 값
    upsert_agent_identity(
        tmp_db,
        agent_id="kimbot",
        did=ident.did,
        erc8004_agent_id=8,
        erc8004_chain="mock:local",
    )
    row2 = get_agent_identity(tmp_db, "kimbot")
    assert row2 is not None
    assert row2.erc8004_agent_id == 8


def test_get_agent_identity_missing_returns_none(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    assert get_agent_identity(tmp_db, "ghost") is None
