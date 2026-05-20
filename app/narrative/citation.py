"""인용 마커 파싱·포맷팅 유틸리티 — Phase 3.0.

마커 형식: ``[↑e<first_8_chars_of_event_id>]``
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 인용 마커 regex: [↑e<8자리 hex>] — case-insensitive (BUG-1 fix v1.0.3).
# Opus 등 일부 LLM이 hex를 대문자로 emit하는 케이스 대응. extract_citations()가
# 추출 후 .lower()로 정규화하므로 event_id[:8] 매칭은 그대로 유효.
_MARKER_PATTERN = re.compile(r"\[↑e([0-9a-fA-F]{8})\]")

# short_id 길이 상수 (plan §10 Q1)
SHORT_ID_LEN = 8


@dataclass(frozen=True)
class Citation:
    """단일 인용 마커를 나타내는 불변 데이터 클래스."""

    short_id: str
    """event_id 앞 8자리 hex."""


def format_marker(event_id: str) -> str:
    """event_id (또는 short_id)를 인용 마커 문자열로 변환한다.

    Args:
        event_id: 전체 UUID 또는 short_id.

    Returns:
        ``[↑e<first_8_chars>]`` 형식의 마커 문자열.
    """
    short_id = event_id[:SHORT_ID_LEN]
    return f"[↑e{short_id}]"


def extract_citations(text: str) -> list[Citation]:
    """텍스트에서 인용 마커를 모두 추출한다. 중복은 제거.

    Args:
        text: 검색 대상 텍스트.

    Returns:
        중복 없는 Citation 목록 (등장 순서 유지).
    """
    seen: set[str] = set()
    result: list[Citation] = []
    for match in _MARKER_PATTERN.finditer(text):
        # BUG-1 fix: normalize captured hex to lowercase so uppercase markers
        # from LLM still resolve against evidence (event_id[:8] is always lowercase).
        sid = match.group(1).lower()
        if sid not in seen:
            seen.add(sid)
            result.append(Citation(short_id=sid))
    return result
