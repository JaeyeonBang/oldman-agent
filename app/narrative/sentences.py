"""인용 마커가 포함된 문장 추출기 — Phase 4.1.

LLM 내러티브 텍스트에서 특정 인용 마커를 포함하는 문장을 추출한다.
judge_grounding 호출 시 claim 문장을 좁혀주는 용도로 사용한다.
"""

from __future__ import annotations

import re

# 문장 경계: [.!?] 뒤에 공백이 오는 위치 (한국어 다./요. 포함)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def extract_sentence_for_marker(text: str, marker: str) -> str | None:
    """텍스트에서 마커를 포함하는 **모든** 문장을 합쳐 반환한다.

    v1.0.6 변경 (이전엔 첫 문장만 반환):
    LLM이 내러티브 첫머리에 "X는 A, B, C 했다 [m1][m2][m3]" 같이 모든 marker를
    aggregate sentence에 몰고, 뒤에 marker별 구체 문장 ("...A를 했다 [m1]",
    "...B를 했다 [m2]")을 별도로 쓰는 경우가 흔하다. 첫 문장만 반환하면
    judge가 aggregate claim vs single payload를 비교하여 ungrounded 판정.
    모든 포함 문장을 합쳐 보내면 specific 문장이 함께 들어가 정확히 grounded.

    알고리즘:
    1. ``r'(?<=[.!?])\\s+'`` 패턴으로 문장을 분리.
    2. marker를 포함하는 모든 문장을 ``" "``로 join하여 반환.
    3. marker가 없으면 None.
    4. 문장 분리 실패(구두점 없음) → 전체 텍스트 반환.

    Args:
        text: 검색 대상 내러티브 텍스트.
        marker: 찾을 인용 마커 문자열 (예: ``[↑e1a2b3c4]``).

    Returns:
        marker를 포함하는 모든 문장을 공백으로 join한 문자열, 없으면 None.
    """
    if marker not in text:
        return None

    sentences = _SENTENCE_SPLIT_RE.split(text)
    matched = [s for s in sentences if marker in s]

    if not matched:
        # 분리 후에도 못 찾으면 (마커가 경계에 걸려 있는 희귀 케이스)
        return text

    return " ".join(matched)
