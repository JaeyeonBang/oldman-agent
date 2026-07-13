"""P2 — 층위 결제: listing fee + citation royalty escrow (TDD).

설계 (plan §3 P2): 매입 대금을 소액 listing fee(즉시) + escrow 잔액으로 분할.
유료 query에서 인용되면 escrow 해제(royalty), 미인용 horizon 경과 시 소멸.
조작 정보는 인용이 안 되므로 구조적으로 listing fee 이상 못 번다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from app.api.publish import OLDMAN_TREASURY_AGENT_ID, execute_publish
from app.api.schemas import PublishRequest
from app.config import Settings
from app.credits.ledger import get_balance
from app.trust.payout import (
    release_royalties_for_citations,
    split_publish_payment,
)

T0 = datetime(2026, 7, 5, 9, 0, 0, tzinfo=UTC)
# credits_transactions.event_id / invoice_id는 UUID 컬럼 — 실제 UUID 필요
EVT1 = str(uuid.uuid4())
INV1 = str(uuid.uuid4())
INV2 = str(uuid.uuid4())


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "db_path": ":memory:",
        "jaccard_window": 50,
        "jaccard_threshold": 0.9,
        "payment_enabled": True,
        "royalty_enabled": True,
        "publish_reward": 5,
        "listing_fee_ratio": 0.2,
        "escrow_horizon_days": 14,
        "starting_grant": 100,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _split(
    conn: duckdb.DuckDBPyConnection, settings: Settings, event_id: str = EVT1
) -> None:
    conn.execute("BEGIN")
    split_publish_payment(
        conn,
        settings,
        event_id=event_id,
        seller_agent="kimbot",
        now=T0,
    )
    conn.execute("COMMIT")


def test_split_pays_listing_fee_and_escrows_rest(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    settings = _settings()
    _split(tmp_db, settings)
    # listing fee = round(5 * 0.2) = 1 즉시 지급
    assert get_balance(tmp_db, "kimbot") == settings.starting_grant + 1
    row = tmp_db.execute(
        "SELECT seller_agent, amount, status FROM royalty_escrows WHERE event_id = ?",
        [EVT1],
    ).fetchone()
    assert row == ("kimbot", 4, "open")


def test_split_with_reward_1_has_no_escrow(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    settings = _settings(publish_reward=1)
    _split(tmp_db, settings)
    assert get_balance(tmp_db, "kimbot") == settings.starting_grant + 1
    assert (
        tmp_db.execute("SELECT COUNT(*) FROM royalty_escrows").fetchone()[0] == 0
    )


def test_release_pays_royalty_once(tmp_db: duckdb.DuckDBPyConnection) -> None:
    settings = _settings()
    _split(tmp_db, settings)
    releases = release_royalties_for_citations(
        tmp_db,
        settings,
        citation_event_ids=[EVT1],
        invoice_id=INV1,
        now=T0 + timedelta(days=1),
    )
    assert len(releases) == 1
    assert releases[0].status == "paid"
    assert releases[0].amount == 4
    assert get_balance(tmp_db, "kimbot") == settings.starting_grant + 5
    # 이중 지급 방지 — 두 번째 인용은 이미 paid라 no-op
    again = release_royalties_for_citations(
        tmp_db,
        settings,
        citation_event_ids=[EVT1],
        invoice_id=INV2,
        now=T0 + timedelta(days=2),
    )
    assert again == []
    assert get_balance(tmp_db, "kimbot") == settings.starting_grant + 5


def test_release_expires_stale_escrow(tmp_db: duckdb.DuckDBPyConnection) -> None:
    settings = _settings()
    _split(tmp_db, settings)
    releases = release_royalties_for_citations(
        tmp_db,
        settings,
        citation_event_ids=[EVT1],
        invoice_id=INV1,
        now=T0 + timedelta(days=15),  # horizon(14일) 경과
    )
    assert len(releases) == 1
    assert releases[0].status == "expired"
    assert get_balance(tmp_db, "kimbot") == settings.starting_grant + 1  # fee만
    row = tmp_db.execute(
        "SELECT status FROM royalty_escrows WHERE event_id = ?",
        [EVT1],
    ).fetchone()
    assert row == ("expired",)


def test_release_without_escrow_is_noop(tmp_db: duckdb.DuckDBPyConnection) -> None:
    settings = _settings()
    assert (
        release_royalties_for_citations(
            tmp_db,
            settings,
            citation_event_ids=[str(uuid.uuid4())],
            invoice_id=INV1,
            now=T0,
        )
        == []
    )


@pytest.mark.asyncio
async def test_publish_with_royalty_creates_escrow_and_trust_event(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    """publish 통합: 분할 지급 + escrow + reliability trust event + 명부 가입."""
    settings = _settings()
    resp = await execute_publish(
        tmp_db,
        settings,
        PublishRequest(
            event_kind="anecdote",
            source_agent="kimbot",
            observed_agent="leebot",
            declared_source_type="third_party",
            payload={"text": "이봇이 새 skill을 공개했다"},
        ),
    )
    assert resp.status == "stored"
    escrow = tmp_db.execute(
        "SELECT seller_agent, amount, status FROM royalty_escrows WHERE event_id = ?",
        [resp.event_id],
    ).fetchone()
    assert escrow == ("kimbot", 4, "open")
    trust_row = tmp_db.execute(
        "SELECT criterion, positive, cause, cause_ref FROM trust_events "
        "WHERE agent_id='kimbot'"
    ).fetchone()
    assert trust_row == ("reliability", True, "publish_settled", resp.event_id)
    member = tmp_db.execute(
        "SELECT state FROM village_registry WHERE agent_id='kimbot'"
    ).fetchone()
    assert member == ("provisional",)
    # treasury에서 listing fee만 즉시 차감 (escrow는 미인용 시 소멸될 가상 계정)
    assert (
        get_balance(tmp_db, OLDMAN_TREASURY_AGENT_ID)
        == settings.starting_grant - 1
    )
