"""Narrative 렌더러 + 재시도 루프 — Phase 3.4 / M4 확장.

cold-start 확인 → evidence 선택 → LLM 호출 → 인용 검증 → 재시도.
모든 예외는 swallow + fallback 반환. HTTP 500 노출 없음.

M4: validator_mode="strict" + judge_provider 파라미터 추가.

⚠️ 이 파일은 CLAUDE.md EVAL 트리거 대상. 변경 시 EVAL-2 재실행 필요.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

import duckdb

from app.api.schemas import Citation as CitationSchema
from app.llm.base import LLMRequest, LLMTier
from app.narrative.citation import Citation
from app.narrative.evidence import Evidence, select_evidence
from app.narrative.prompts import build_user_message, load_narrative_prompt
from app.narrative.validator import validate_citations, validate_citations_with_judge
from app.state.cold_start import COLD_START_FALLBACK_MESSAGE, get_cold_start_state

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class NarrativeRendererResult:
    """render_narrative 반환값 (불변)."""

    answer: str
    citations: list[CitationSchema]
    retries_used: int
    is_cold_start: bool
    used_fallback: bool


def _fallback(*, is_cold_start: bool = False, retries_used: int = 0) -> NarrativeRendererResult:
    return NarrativeRendererResult(
        answer=COLD_START_FALLBACK_MESSAGE,
        citations=[],
        retries_used=retries_used,
        is_cold_start=is_cold_start,
        used_fallback=True,
    )


async def render_narrative(
    conn: duckdb.DuckDBPyConnection,
    provider: Any,
    question: str,
    subject_agent: str | None,
    *,
    max_retries: int = 2,
    validator_mode: Literal["existence", "strict"] = "existence",
    judge_provider: Any | None = None,
) -> NarrativeRendererResult:
    """내러티브를 생성한다.

    단계:
    1. cold-start 확인 → cold이면 fallback 즉시 반환 (provider 미호출).
    2. evidence 선택. 빈 evidence이면 fallback.
    3. 최대 max_retries+1 회 LLM 호출 + 인용 검증 루프.
    4. 검증 성공 시 결과 반환. 모든 시도 실패 시 fallback.
    5. 모든 예외는 swallow + fallback. HTTP 500 노출 없음.

    Args:
        conn: DuckDB 연결.
        provider: LLMProvider 호환 객체.
        question: 사용자 질문.
        subject_agent: 대상 에이전트 이름 (None이면 전체).
        max_retries: 검증 실패 후 최대 재시도 횟수 (기본 2 → 총 3회).
        validator_mode: "existence" (M3 기본) 또는 "strict" (M4 LLM judge).
        judge_provider: strict 모드 전용 judge LLMProvider.
            strict 모드에서 None이면 ValueError 즉시 발생.

    Returns:
        NarrativeRendererResult 불변 객체.

    Raises:
        ValueError: validator_mode="strict" 이고 judge_provider=None 인 경우.
    """
    # strict 모드 guard
    if validator_mode == "strict" and judge_provider is None:
        raise ValueError(
            "validator_mode='strict' 사용 시 judge_provider를 반드시 전달해야 합니다. "
            "API 레이어에서 app.state.judge_provider를 주입하거나 "
            "validator_mode='existence'를 사용하세요."
        )
    # 1. cold-start 확인
    try:
        cold_state = get_cold_start_state(conn)
    except Exception as exc:
        _LOG.warning("renderer: cold_start 확인 실패: %s", exc)
        return _fallback(is_cold_start=True)

    if cold_state.is_cold:
        return _fallback(is_cold_start=True)

    # 2. evidence 선택
    try:
        evidence = select_evidence(conn, subject_agent=subject_agent)
    except Exception as exc:
        _LOG.warning("renderer: evidence 선택 실패: %s", exc)
        return _fallback()

    if not evidence.events:
        return _fallback()

    # 3. 시스템 프롬프트 로드
    try:
        system_prompt = load_narrative_prompt()
    except Exception as exc:
        _LOG.warning("renderer: 프롬프트 로드 실패: %s", exc)
        return _fallback()

    # 4. 재시도 루프 (총 max_retries+1 회)
    retries_used = 0
    user_message = build_user_message(question, evidence, subject_agent=subject_agent)
    _last_ungrounded: bool = False  # 재시도 힌트 결정용

    for attempt in range(max_retries + 1):
        if attempt > 0:
            retries_used += 1
            # 재시도 힌트: ungrounded vs missing에 따라 다른 메시지
            if _last_ungrounded:
                hint = (
                    "\n\n[재시도 힌트] 이전 응답의 주장이 인용한 event 내용과 일치하지 않습니다. "
                    "인용한 evidence를 정확히 반영하세요."
                )
            else:
                hint = (
                    "\n\n[재시도 힌트] 이전 응답의 인용에 실재하지 않는 event_id가 있었습니다. "
                    "제공된 evidence만 사용하세요."
                )
            user_message_with_hint = user_message + hint
        else:
            user_message_with_hint = user_message

        # LLM 호출
        try:
            response = await provider.complete(
                LLMRequest(
                    system=system_prompt,
                    prompt=user_message_with_hint,
                    tier=LLMTier.EXPENSIVE,
                    max_tokens=1024,
                )
            )
        except Exception as exc:
            _LOG.warning("renderer: LLM 호출 실패 (attempt=%d): %s", attempt, exc)
            return _fallback(retries_used=retries_used)

        answer_text = response.text

        # 인용 검증 (existence 또는 strict)
        if validator_mode == "strict":
            # judge_provider is not None (guard 위에서 확인)
            validation = await validate_citations_with_judge(
                answer_text, evidence, judge_provider
            )
            _last_ungrounded = len(validation.ungrounded) > 0
        else:
            validation = validate_citations(answer_text, evidence)
            _last_ungrounded = False

        if validation.is_valid:
            # 검증 통과 → citations 구성 후 반환
            citations = _build_citations(validation.extracted, evidence)
            return NarrativeRendererResult(
                answer=answer_text,
                citations=citations,
                retries_used=retries_used,
                is_cold_start=False,
                used_fallback=False,
            )

        _LOG.info(
            "renderer: 인용 검증 실패 (attempt=%d, missing=%s, ungrounded=%s)",
            attempt,
            validation.missing,
            [c.short_id for c in validation.ungrounded],
        )

    # 5. 모든 시도 소진 → fallback
    return _fallback(retries_used=retries_used)


def _build_citations(
    extracted: list[Citation],
    evidence: Evidence,
) -> list[CitationSchema]:
    """추출된 Citation을 event_id와 매핑해 CitationSchema 목록으로 변환."""
    short_to_full: dict[str, str] = {ev.event_id[:8]: ev.event_id for ev in evidence.events}
    return [
        CitationSchema(short_id=c.short_id, event_id=short_to_full.get(c.short_id))
        for c in extracted
    ]
