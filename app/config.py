"""Runtime settings (env-overridable).

DuckDB is single-writer — uvicorn MUST run with ``--workers 1``. ``db_path``
defaults to ``./oldman.duckdb`` (gitignored) and is overridable via
``OLDMAN_DB_PATH``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str
    jaccard_window: int
    jaccard_threshold: float
    # v1.5 alpha — credits ledger (off-chain).
    payment_enabled: bool = False
    publish_reward: int = 1
    query_price: int = 1
    starting_grant: int = 100
    invoice_ttl_seconds: int = 300
    # Kill-switch (PRD D8 / outside voice T7c): trips ledger to noop + log.
    payment_kill_switch: bool = False
    # v2 P0 — trust identity. require=True면 무서명 publish 거부.
    require_signed_publish: bool = False
    erc8004_mode: str = "mock"
    # v2 P2 — 층위 결제 (listing fee + citation royalty escrow).
    royalty_enabled: bool = False
    listing_fee_ratio: float = 0.2
    escrow_horizon_days: int = 14
    # v2 P4 — 환불 풀 (정산 query당 적립, 0이면 off).
    refund_pool_fee: int = 0
    # oldman 자신의 did:key seed (32B hex). 미설정 시 카드에 DID 미게재.
    oldman_did_seed: str | None = None

    def __post_init__(self) -> None:
        # 결제 금액 하한 — credits_transfer는 amount>0을 요구하므로 0/음수면
        # publish/query가 매핑 안 된 예외로 크래시한다(H3). 경계에서 조기 거부.
        if self.publish_reward < 1:
            raise ValueError(f"publish_reward must be >= 1, got {self.publish_reward}")
        if self.query_price < 1:
            raise ValueError(f"query_price must be >= 1, got {self.query_price}")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            db_path=os.environ.get("OLDMAN_DB_PATH", "./oldman.duckdb"),
            jaccard_window=int(os.environ.get("OLDMAN_JACCARD_WINDOW", "50")),
            jaccard_threshold=float(os.environ.get("OLDMAN_JACCARD_THRESHOLD", "0.9")),
            payment_enabled=os.environ.get("OLDMAN_PAYMENT_ENABLED", "false").lower()
            in ("1", "true", "yes"),
            publish_reward=int(os.environ.get("OLDMAN_PUBLISH_REWARD", "1")),
            query_price=int(os.environ.get("OLDMAN_QUERY_PRICE", "1")),
            starting_grant=int(os.environ.get("OLDMAN_STARTING_GRANT", "100")),
            invoice_ttl_seconds=int(
                os.environ.get("OLDMAN_INVOICE_TTL_SECONDS", "300")
            ),
            payment_kill_switch=os.environ.get(
                "OLDMAN_PAYMENT_KILL_SWITCH", "false"
            ).lower()
            in ("1", "true", "yes"),
            require_signed_publish=os.environ.get(
                "OLDMAN_REQUIRE_SIGNED_PUBLISH", "false"
            ).lower()
            in ("1", "true", "yes"),
            erc8004_mode=os.environ.get("OLDMAN_ERC8004_MODE", "mock"),
            oldman_did_seed=os.environ.get("OLDMAN_DID_SEED") or None,
            royalty_enabled=os.environ.get("OLDMAN_ROYALTY_ENABLED", "false").lower()
            in ("1", "true", "yes"),
            listing_fee_ratio=float(
                os.environ.get("OLDMAN_LISTING_FEE_RATIO", "0.2")
            ),
            escrow_horizon_days=int(
                os.environ.get("OLDMAN_ESCROW_HORIZON_DAYS", "14")
            ),
            refund_pool_fee=int(os.environ.get("OLDMAN_REFUND_POOL_FEE", "0")),
        )


def get_settings() -> Settings:
    return Settings.from_env()
