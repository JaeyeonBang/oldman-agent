"""H3 회귀 — Settings 결제 파라미터 하한 검증.

publish_reward/query_price가 0(또는 음수)이면 credits_transfer(amount>0)가
InvalidAgentError를 던져 publish/query 경로가 매핑 안 된 예외로 깨진다.
경계에서 조기 거부해 잘못된 설정이 런타임 크래시로 새지 않게 한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings


def _base(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "db_path": ":memory:",
        "jaccard_window": 50,
        "jaccard_threshold": 0.9,
    }
    d.update(kw)
    return d


def test_publish_reward_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Settings(**_base(publish_reward=0))


def test_query_price_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Settings(**_base(query_price=-1))


def test_valid_settings_construct() -> None:
    s = Settings(**_base())
    assert s.publish_reward >= 1
    assert s.query_price >= 1
