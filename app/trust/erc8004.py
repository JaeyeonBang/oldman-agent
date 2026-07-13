"""ERC-8004 Identity Registry 클라이언트 — mock 기본, testnet은 후속 스크립트.

produce-only 원칙 (research/agent-trust-2026-07.md §2.1): 우리는 표준 준수
발행자다 — 등록 파일을 발행하고 (P4에서 giveFeedback 미러 예정), 타인의
온체인 평판 점수를 신뢰 판단의 입력으로 소비하지 않는다 (sybil 실증 회피).

mock이 기본 (``OLDMAN_ERC8004_MODE=mock``) — RPC 없이 데모가 돌아야 한다는
pivot 원칙. 실제 testnet 등록(web3 + erc-8004-py)은 ``scripts/``로 분리 예정.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ERC8004Registration:
    agent_id: int
    agent_domain: str
    did: str
    chain: str
    registration_file: dict[str, Any]


class MockERC8004IdentityRegistry:
    """인메모리 Identity Registry — agentId 순차 발급, 도메인당 idempotent.

    EIP-8004 Identity Registry의 계약 표면(register → agentId, tokenURI →
    registration file)만 모사한다. 온체인 세부(ERC-721 mint, 가스)는 생략.
    """

    def __init__(self, chain: str = "mock:local") -> None:
        self._chain = chain
        self._by_domain: dict[str, ERC8004Registration] = {}
        self._by_id: dict[int, ERC8004Registration] = {}

    def register(
        self, *, agent_domain: str, did: str, a2a_endpoint: str
    ) -> ERC8004Registration:
        existing = self._by_domain.get(agent_domain)
        if existing is not None:
            return existing
        agent_id = len(self._by_id) + 1
        reg = ERC8004Registration(
            agent_id=agent_id,
            agent_domain=agent_domain,
            did=did,
            chain=self._chain,
            registration_file={
                "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
                "name": agent_domain,
                "did": did,
                "endpoints": [
                    {
                        "name": "A2A",
                        "endpoint": f"{a2a_endpoint}/.well-known/agent-card.json",
                        "version": "0.3.0",
                    }
                ],
                "supportedTrust": ["feedback"],
            },
        )
        self._by_domain[agent_domain] = reg
        self._by_id[agent_id] = reg
        return reg

    def get(self, agent_id: int) -> ERC8004Registration | None:
        return self._by_id.get(agent_id)


@dataclass(frozen=True)
class ERC8004Feedback:
    agent_id: int
    score: int  # 0-100 (EIP-8004 giveFeedback)
    tag: str


class MockERC8004ReputationRegistry:
    """Reputation Registry 미러 (P4, produce-only).

    ``giveFeedback(agentId, score, tag)`` 표면만 모사 — 꼰대의 제재/평판
    판정을 발행한다. 타인의 온체인 피드백을 읽어 신뢰 입력으로 쓰는 API는
    의도적으로 제공하지 않는다 (sybil 실증 회피 원칙).
    """

    def __init__(self) -> None:
        self._feedbacks: list[ERC8004Feedback] = []

    def give_feedback(
        self, *, agent_id: int, score: int, tag: str
    ) -> ERC8004Feedback:
        if not 0 <= score <= 100:
            raise ValueError(f"score must be 0-100, got {score}")
        fb = ERC8004Feedback(agent_id=agent_id, score=score, tag=tag)
        self._feedbacks.append(fb)
        return fb

    def feedbacks_for(self, agent_id: int) -> list[ERC8004Feedback]:
        return [f for f in self._feedbacks if f.agent_id == agent_id]
