"""Narrative 프롬프트 로더 및 사용자 메시지 빌더 — Phase 3.2 / Phase 7.5.

prompts/narrative_neutral.md 또는 prompts/narrative_kkondae.md 를 시스템 프롬프트로 사용.
OLDMAN_PERSONA 환경변수 또는 load_narrative_prompt(persona=...) 인자로 선택.
build_user_message 는 Evidence를 LLM 사용자 메시지 포맷으로 변환한다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.narrative.citation import format_marker
from app.narrative.evidence import Evidence

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# Phase 7.5: persona → prompt file mapping
_PERSONA_FILE_MAP: dict[str, Path] = {
    "neutral": _PROMPTS_DIR / "narrative_neutral.md",
    "kkondae": _PROMPTS_DIR / "narrative_kkondae.md",
}


def load_narrative_prompt(persona: str | None = None) -> str:
    """페르소나에 맞는 narrative 시스템 프롬프트를 반환한다.

    Args:
        persona: "neutral" | "kkondae" | None.
                 None이면 OLDMAN_PERSONA 환경변수를 읽고, 없으면 "neutral".

    Returns:
        시스템 프롬프트 텍스트.

    Raises:
        ValueError: 알 수 없는 persona 이름이면.
        FileNotFoundError: 해당 prompts/*.md 파일이 없으면.
    """
    p = persona or os.environ.get("OLDMAN_PERSONA", "neutral")
    if p not in _PERSONA_FILE_MAP:
        raise ValueError(
            f"unknown persona '{p}'; valid: {list(_PERSONA_FILE_MAP)}"
        )
    return _PERSONA_FILE_MAP[p].read_text(encoding="utf-8")


def build_user_message(
    question: str,
    evidence: Evidence,
    *,
    subject_agent: str | None = None,
) -> str:
    """질문과 Evidence를 LLM 사용자 메시지로 직렬화한다.

    Args:
        question: 사용자 질문.
        evidence: select_evidence 가 반환한 Evidence 객체.
        subject_agent: 대상 에이전트 이름 (None이면 "전체").

    Returns:
        LLM에 전달할 사용자 메시지 문자열.
    """
    subject_label = subject_agent if subject_agent is not None else "전체"

    # 이벤트 목록 포맷팅
    if evidence.events:
        event_lines: list[str] = []
        for ev in evidence.events:
            marker = format_marker(ev.event_id)
            ts_str = ev.ts.isoformat() if hasattr(ev.ts, "isoformat") else str(ev.ts)
            observed = "-"
            payload_str = json.dumps(ev.payload, ensure_ascii=False)
            # payload가 길면 200자로 잘라냄
            if len(payload_str) > 200:
                payload_str = payload_str[:197] + "..."
            event_lines.append(
                f"{marker} {ev.kind} · {ev.source_agent} → {observed} · {ts_str}\n"
                f"  payload: {payload_str}"
            )
        events_section = "\n".join(event_lines)
    else:
        events_section = "(없음)"

    # Reflection 목록 포맷팅
    if evidence.reflections:
        ref_lines: list[str] = []
        for ref in evidence.reflections:
            ref_lines.append(
                f"[scope={ref.scope} subject={ref.subject}] {ref.text}"
            )
        reflections_section = "\n".join(ref_lines)
    else:
        reflections_section = "(없음)"

    return (
        f"질문: {question}\n\n"
        f"대상: {subject_label}\n\n"
        f"수집된 이벤트 (최근순):\n{events_section}\n\n"
        f"수집된 reflection (최근순):\n{reflections_section}\n\n"
        f"위 증거만 사용하여 한국어로 답하세요. 모든 주장에 [↑e<short_id>] 인용을 첨부하세요."
    )
