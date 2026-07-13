"""F1 인라인 배선 — 축출(excluded) 판매자는 live publish에서 차단 (TDD).

외부 아키텍처 검토 결함 F1: 제재 상태('excluded')는 membership 상태기계가
판정하지만, 그 '집행'(price_adjustment(state).allowed=False)이 live publish
경로에서 소비되지 않았다 — 축출된 판매자가 여전히 팔고 보상받을 수 있었다.
이 테스트는 축출이 publish에서 실제로 '무는지'를 고정한다.

시나리오:
  ① 축출된 판매자 publish → ExcludedSellerError, 아무 event/결제 없음
  ② member 판매자 publish → 정상 저장 (대조군, 회귀 방지)
  ③ 축출은 서명이 유효해도 차단 (제재가 서명보다 우선)
"""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from app.api.publish import ExcludedSellerError, execute_publish
from app.api.schemas import PublishRequest
from app.config import Settings
from app.storage.trust import upsert_membership
from app.trust.identity import generate_identity, sign_payload

T0 = datetime(2026, 7, 14, 9, 0, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "db_path": ":memory:",
        "jaccard_window": 50,
        "jaccard_threshold": 0.9,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _req(payload: dict[str, object], **kw: object) -> PublishRequest:
    return PublishRequest(
        event_kind="anecdote",
        source_agent="kimbot",
        observed_agent="leebot",
        declared_source_type="third_party",
        payload=payload,
        **kw,  # type: ignore[arg-type]
    )


def _seed_state(conn: duckdb.DuckDBPyConnection, agent_id: str, state: str) -> None:
    upsert_membership(
        conn,
        agent_id=agent_id,
        state=state,  # type: ignore[arg-type]
        violation_count=4 if state == "excluded" else 0,
        joined_at=T0,
        state_changed_at=T0,
    )


@pytest.mark.asyncio
async def test_excluded_seller_blocked_at_publish(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    _seed_state(tmp_db, "kimbot", "excluded")
    with pytest.raises(ExcludedSellerError):
        await execute_publish(tmp_db, _settings(), _req({"text": "출입금지인데 팔려 함"}))
    # 아무 event도 저장되지 않고, 결제도 없어야 한다
    assert tmp_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_member_seller_publishes_normally(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    _seed_state(tmp_db, "kimbot", "member")
    resp = await execute_publish(tmp_db, _settings(), _req({"text": "정상 판매자"}))
    assert resp.status == "stored"


@pytest.mark.asyncio
async def test_exclusion_overrides_valid_signature(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    """제재는 서명 유효성보다 우선 — 서명이 완벽해도 축출자는 못 판다."""
    _seed_state(tmp_db, "kimbot", "excluded")
    ident = generate_identity()
    payload: dict[str, object] = {"text": "서명은 멀쩡하지만 출입금지"}
    sig = sign_payload(ident.seed_hex, payload, "kimbot")
    with pytest.raises(ExcludedSellerError):
        await execute_publish(
            tmp_db,
            _settings(),
            _req(payload, seller_did=ident.did, payload_signature=sig),
        )
    assert tmp_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
