"""ERC-8004 Identity Registry testnet 실등록 — P5 스크립트 (dry-run 기본).

produce-only 원칙: 등록 파일을 발행할 뿐, 온체인 평판을 소비하지 않는다.
registration file은 base64 data: URI로 완전 온체인 게재 (IPFS 불요 — EIP 허용).

준비:
    uv sync --extra chain          # erc-8004-py (+web3) 설치
    export OLDMAN_ERC8004_RPC_URL=https://...      # e.g. BNB testnet / Base Sepolia
    export OLDMAN_ERC8004_PRIVATE_KEY=0x...        # 테스트 지갑 (실자산 금지!)
    export OLDMAN_ERC8004_IDENTITY_REGISTRY=0x...  # 대상 체인의 Identity Registry
    export OLDMAN_ERC8004_CHAIN_ID=97              # e.g. 97=BNB testnet
    export OLDMAN_AGENT_DOMAIN=oldman-agent.example
    export OLDMAN_BASE_URL=https://oldman-agent.example
    export OLDMAN_DID_SEED=<32B hex>               # 카드와 동일 DID 게재

Run:
    uv run python scripts/erc8004_register.py            # dry-run (기본)
    uv run python scripts/erc8004_register.py --execute  # 실등록

주의: 레지스트리 주소·ABI는 배포 시점 원문(EIP + erc-8004 공식 contracts repo)
재확인 필수 — 스펙이 분기 단위로 움직인다 (research/agent-trust-2026-07.md §6).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from typing import Any


def _build_registration_file(domain: str, base_url: str, did: str | None) -> dict[str, Any]:
    """mock(app/trust/erc8004.py)과 동일 shape — 데모/실등록 일관성."""
    file: dict[str, Any] = {
        "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        "name": domain,
        "endpoints": [
            {
                "name": "A2A",
                "endpoint": f"{base_url}/.well-known/agent-card.json",
                "version": "0.3.0",
            }
        ],
        "supportedTrust": ["feedback"],
    }
    if did:
        file["did"] = did
    return file


def _token_uri(registration_file: dict[str, Any]) -> str:
    raw = json.dumps(registration_file, ensure_ascii=False).encode("utf-8")
    return "data:application/json;base64," + base64.b64encode(raw).decode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute", action="store_true", help="실제 testnet 등록 (기본: dry-run)"
    )
    args = parser.parse_args()

    domain = os.environ.get("OLDMAN_AGENT_DOMAIN", "oldman-agent.example")
    base_url = os.environ.get("OLDMAN_BASE_URL", "http://localhost:8080")
    did: str | None = None
    seed = os.environ.get("OLDMAN_DID_SEED")
    if seed:
        from app.trust.identity import did_from_seed

        did = did_from_seed(seed)

    registration_file = _build_registration_file(domain, base_url, did)
    token_uri = _token_uri(registration_file)

    print("registration file:")
    print(json.dumps(registration_file, ensure_ascii=False, indent=2))
    print(f"\ntoken_uri ({len(token_uri)} chars): {token_uri[:80]}…")

    if not args.execute:
        print("\n[dry-run] --execute 로 실등록. 필요 env는 파일 상단 docstring 참조.")
        return

    rpc_url = os.environ.get("OLDMAN_ERC8004_RPC_URL")
    private_key = os.environ.get("OLDMAN_ERC8004_PRIVATE_KEY")
    registry = os.environ.get("OLDMAN_ERC8004_IDENTITY_REGISTRY")
    chain_id = os.environ.get("OLDMAN_ERC8004_CHAIN_ID")
    missing = [
        name
        for name, val in [
            ("OLDMAN_ERC8004_RPC_URL", rpc_url),
            ("OLDMAN_ERC8004_PRIVATE_KEY", private_key),
            ("OLDMAN_ERC8004_IDENTITY_REGISTRY", registry),
            ("OLDMAN_ERC8004_CHAIN_ID", chain_id),
        ]
        if not val
    ]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)}")

    try:
        from erc8004.adapters import Web3Adapter  # type: ignore[import-untyped]
        from erc8004.client import ERC8004Client  # type: ignore[import-untyped]
        from erc8004.types import ContractAddresses  # type: ignore[import-untyped]
        from web3 import Web3
    except ImportError:
        sys.exit("erc-8004-py 미설치 — `uv sync --extra chain` 후 재실행")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        sys.exit(f"RPC 연결 실패: {rpc_url}")
    adapter = Web3Adapter(w3, private_key=private_key)
    client = ERC8004Client(
        adapter,
        ContractAddresses(
            identityRegistry=str(registry),
            reputationRegistry=os.environ.get("OLDMAN_ERC8004_REPUTATION_REGISTRY", ""),
            validationRegistry=os.environ.get("OLDMAN_ERC8004_VALIDATION_REGISTRY", ""),
            chainId=int(str(chain_id)),
        ),
    )
    result = client.identity.register_with_uri(token_uri)
    print("\n등록 결과:")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(
        "\n다음 단계: 결과의 agentId를 OLDMAN_ERC8004_AGENT_ID env로 설정하면 "
        "AgentCard x-oldman에 게재된다."
    )


if __name__ == "__main__":
    main()
