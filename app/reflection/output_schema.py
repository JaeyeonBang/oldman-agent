"""LLM 출력 스키마 — Phase 2.4.

TraitsCompiled: 반성 결과 JSON의 pydantic 모델.
LLM이 반환한 텍스트를 model_validate_json 으로 파싱하여 검증.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TraitsCompiled(BaseModel):
    """Reflection LLM 출력 계약.

    형식:
        {
          "summary": str,
          "descriptors": list[str],
          "evidence_event_ids": list[str]
        }
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str
    descriptors: list[str]
    evidence_event_ids: list[str]
