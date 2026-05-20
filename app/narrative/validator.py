"""인용 검증기 — Phase 3.3 / M4 확장.

LLM 응답에서 추출한 [↑e<short_id>] 마커가
실제 evidence의 event_id 앞 8자리와 일치하는지 확인한다.

M3: 존재 여부(existence-only) 검사.
M4: 내용 기반 LLM 판정(content-grounded judge) — validate_citations_with_judge 추가.

⚠️ 이 파일은 CLAUDE.md EVAL 트리거 대상. 변경 시 EVAL-2 재실행 필요.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.narrative.citation import Citation, extract_citations
from app.narrative.evidence import Evidence

_LOG = logging.getLogger(__name__)

# 비자명 텍스트 최소 길이: 이 길이 초과 텍스트에 마커가 없으면 invalid
_NON_TRIVIAL_MIN_LEN = 20


@dataclass(frozen=True)
class ValidationResult:
    """validate_citations / validate_citations_with_judge 반환값 (불변)."""

    is_valid: bool
    missing: list[str]
    """evidence에 없는 short_id 목록."""
    extracted: list[Citation]
    """텍스트에서 추출된 Citation 목록."""
    ungrounded: list[Citation] = field(default_factory=list)
    """judge가 근거 없음으로 판정한 Citation 목록 (M4 strict path)."""


def validate_citations(text: str, evidence: Evidence) -> ValidationResult:
    """LLM 응답 텍스트의 인용 마커를 검증한다.

    알고리즘 (M3 단순 존재 검사):
    1. 텍스트에서 모든 [↑e<short_id>] 마커를 추출한다.
    2. 각 short_id가 evidence.events의 event_id 앞 8자리와 일치하는지 확인한다.
    3. 일치하지 않는 마커가 있으면 → invalid, missing에 해당 short_id 추가.
    4. 마커가 없고 텍스트가 비자명(>20자)이며 evidence.events가 있으면 → invalid.
    5. 그 외 → valid.

    Args:
        text: 검증할 텍스트 (LLM 응답).
        evidence: 근거로 사용된 Evidence 객체.

    Returns:
        ValidationResult 불변 객체.
    """
    extracted = extract_citations(text)

    # evidence의 event_id → short_id 집합 구성
    valid_short_ids: set[str] = {ev.event_id[:8] for ev in evidence.events}

    if extracted:
        # 마커가 있는 경우: 각 마커가 evidence에 존재하는지 확인
        missing: list[str] = [
            c.short_id for c in extracted if c.short_id not in valid_short_ids
        ]
        is_valid = len(missing) == 0
        return ValidationResult(is_valid=is_valid, missing=missing, extracted=extracted)

    # 마커가 없는 경우
    # evidence가 비어 있으면: 증거 없음 → fallback 경로 → valid
    if not evidence.events:
        return ValidationResult(is_valid=True, missing=[], extracted=[])

    # BUG-3 fix v1.0.3: evidence가 존재하면 길이와 무관하게 invalid.
    # 이전 버전은 ≤20자 텍스트(예: mock의 "증거가 부족합니다.")를 valid 처리해
    # cold-start 신호 contract를 깨뜨렸음 (used_fallback=False로 위장 성공).
    # 인용해야 할 evidence가 있는데 마커가 없으면 retry → fallback이 옳음.
    return ValidationResult(is_valid=False, missing=[], extracted=[])


async def validate_citations_with_judge(
    text: str,
    evidence: Evidence,
    judge_provider: Any,
) -> ValidationResult:
    """LLM judge를 사용한 내용 기반 인용 검증 (M4 strict mode).

    알고리즘:
    1. 존재 검증(validate_citations) 먼저 실행.
       실패(missing 있음)이면 judge 호출 없이 즉시 반환.
    2. 각 인용에 대해 문장 추출 → 이벤트 페이로드 조회 → judge 호출.
    3. is_grounded=False인 인용 → ungrounded 목록에 추가.
       judge provider 예외 → graceful degradation: 해당 인용은 grounded 취급.
    4. missing 없고 ungrounded 없으면 is_valid=True.

    Args:
        text: 검증할 텍스트 (LLM 응답).
        evidence: 근거로 사용된 Evidence 객체.
        judge_provider: LLMProvider 호환 객체 (judge 호출용).

    Returns:
        ValidationResult 불변 객체 (ungrounded 필드 포함).
    """
    from app.narrative.citation import format_marker
    from app.narrative.judge import judge_grounding
    from app.narrative.sentences import extract_sentence_for_marker

    # 1. 존재 검증 먼저
    existence_result = validate_citations(text, evidence)
    if not existence_result.is_valid:
        # 존재 실패 → judge 불필요, 즉시 반환
        return existence_result

    # evidence short_id → payload 매핑
    short_to_payload: dict[str, dict[str, Any]] = {
        ev.event_id[:8]: ev.payload for ev in evidence.events
    }

    # 2. 각 인용에 대해 judge 호출
    ungrounded: list[Citation] = []
    for citation in existence_result.extracted:
        marker = format_marker(citation.short_id)
        sentence = extract_sentence_for_marker(text, marker) or text
        payload = short_to_payload.get(citation.short_id, {})

        try:
            verdict = await judge_grounding(judge_provider, sentence, payload)
        except Exception as exc:
            # provider 예외 → graceful degradation: grounded 취급
            _LOG.warning(
                "validator: judge 예외 발생, grounded 취급: short_id=%s err=%s",
                citation.short_id,
                exc,
            )
            continue

        if verdict.reason in ("provider_error", "parse_error"):
            # graceful degradation: judge LLM 오류 시 인용을 reject하지 않고
            # 존재 검증으로 fall back (plan §4 Q4.8). v1.0.5: parse_error 포함.
            _LOG.info(
                "validator: judge %s, grounded로 처리: short_id=%s",
                verdict.reason,
                citation.short_id,
            )
            continue

        if not verdict.is_grounded:
            ungrounded.append(citation)

    is_valid = len(ungrounded) == 0
    return ValidationResult(
        is_valid=is_valid,
        missing=[],
        extracted=existence_result.extracted,
        ungrounded=ungrounded,
    )
