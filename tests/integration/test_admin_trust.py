"""개선 ② — /admin/trust 관측 endpoint (TDD).

빈 DB에서도 전 섹션이 존재하고 회계 감사가 balanced여야 한다.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_trust_overview_shape(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/trust")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "village_registry",
        "trust_scores",
        "recent_trust_events",
        "escrows_by_status",
        "credits_audit",
    ):
        assert key in body, key
    assert body["credits_audit"]["balanced"] is True
    assert body["credits_audit"]["issues"] == []
    assert body["village_registry"] == []  # 빈 DB — 아직 아무도 가입 안 함
