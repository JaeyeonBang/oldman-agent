"""P0 — publish 경로 서명 검증 (TDD).

시나리오:
  ① 서명 publish → stored + events.seller_did 기록
  ② 변조 서명 → InvalidSignatureError (blocked/invalid_signature)
  ③ DID만 있고 서명 없음 → InvalidSignatureError
  ④ require_signed_publish=True + 무서명 → MissingSignatureError
  ⑤ legacy 무서명 publish (require=False) → stored, seller_did NULL (하위 호환)
"""

from __future__ import annotations

import duckdb
import pytest

from app.api.publish import (
    InvalidSignatureError,
    MissingSignatureError,
    execute_publish,
)
from app.api.schemas import PublishRequest
from app.config import Settings
from app.trust.identity import generate_identity, sign_payload


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


@pytest.mark.asyncio
async def test_signed_publish_stores_seller_did(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    ident = generate_identity()
    payload: dict[str, object] = {"text": "이봇이 약속을 지켰다"}
    sig = sign_payload(ident.seed_hex, payload)
    resp = await execute_publish(
        tmp_db,
        _settings(),
        _req(payload, seller_did=ident.did, payload_signature=sig),
    )
    assert resp.status == "stored"
    row = tmp_db.execute(
        "SELECT seller_did FROM events WHERE event_id = ?", [resp.event_id]
    ).fetchone()
    assert row is not None
    assert row[0] == ident.did


@pytest.mark.asyncio
async def test_tampered_signature_blocked(tmp_db: duckdb.DuckDBPyConnection) -> None:
    ident = generate_identity()
    sig = sign_payload(ident.seed_hex, {"text": "원본"})
    with pytest.raises(InvalidSignatureError):
        await execute_publish(
            tmp_db,
            _settings(),
            _req({"text": "변조"}, seller_did=ident.did, payload_signature=sig),
        )
    # 아무 event도 저장되지 않음
    assert tmp_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_did_without_signature_blocked(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    ident = generate_identity()
    with pytest.raises(InvalidSignatureError):
        await execute_publish(
            tmp_db,
            _settings(),
            _req({"text": "x"}, seller_did=ident.did),
        )


@pytest.mark.asyncio
async def test_require_signed_publish_rejects_unsigned(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(MissingSignatureError):
        await execute_publish(
            tmp_db,
            _settings(require_signed_publish=True),
            _req({"text": "x"}),
        )


@pytest.mark.asyncio
async def test_legacy_unsigned_publish_still_works(
    tmp_db: duckdb.DuckDBPyConnection,
) -> None:
    resp = await execute_publish(tmp_db, _settings(), _req({"text": "무서명 구버전"}))
    assert resp.status == "stored"
    row = tmp_db.execute(
        "SELECT seller_did FROM events WHERE event_id = ?", [resp.event_id]
    ).fetchone()
    assert row is not None
    assert row[0] is None
