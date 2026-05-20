"""Reflection 프롬프트 로더 및 사용자 메시지 빌더 — Phase 2.2.

prompts/ 디렉토리의 Markdown 파일을 읽어 (system, user_template) 쌍을 반환.
build_user_message는 이벤트 목록을 LLM 입력 텍스트로 변환한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# 지원하는 scope 값
_VALID_SCOPES = {"agent", "pair", "society"}

# 사용자 메시지 템플릿 (scope 무관 공통)
_USER_TEMPLATE = """아래는 최근 {n}개 이벤트 목록이다. 이를 분석하여 지정된 JSON 형식으로 반성(reflection)을 생성하라.

## 이벤트 목록

{event_lines}

## 출력 형식 (순수 JSON, 다른 텍스트 없음)

{{"summary": "...", "descriptors": ["..."], "evidence_event_ids": ["..."]}}
"""


def load_prompt(scope: str) -> tuple[str, str]:
    """scope에 해당하는 (system_prompt, user_template) 쌍을 반환한다.

    Args:
        scope: 'agent' | 'pair' | 'society'

    Returns:
        (system_prompt_text, user_template_text) 튜플.

    Raises:
        ValueError: scope가 알 수 없는 값일 때.
    """
    if scope not in _VALID_SCOPES:
        raise ValueError(f"unknown scope: {scope!r}. 유효한 값: {sorted(_VALID_SCOPES)}")

    prompt_file = _PROMPTS_DIR / f"reflection_{scope}.md"
    system = prompt_file.read_text(encoding="utf-8")
    return system, _USER_TEMPLATE


def build_user_message(
    events: list[dict[str, Any]],
    *,
    n: int = 10,
) -> str:
    """이벤트 목록을 LLM 사용자 메시지로 직렬화한다.

    Args:
        events: 이벤트 dict 목록. 각 항목에 event_id, kind, payload 키가 있어야 함.
        n: 포함할 최근 이벤트 수 (기본 10). 초과분은 오래된 것부터 제거.

    Returns:
        LLM에 전달할 사용자 메시지 문자열.
    """
    if not events:
        return (
            "분석할 이벤트가 없습니다. 이벤트가 누적된 후 다시 반성을 시도하세요.\n\n"
            '{"summary": "이벤트 없음", "descriptors": ["데이터_없음"], "evidence_event_ids": []}'
        )

    # 최근 n개만 취함 (뒤에서 n개)
    recent = events[-n:]
    lines: list[str] = []
    for evt in recent:
        event_id = evt.get("event_id", "unknown")
        kind = evt.get("kind", "unknown")
        payload = evt.get("payload", {})
        payload_str = json.dumps(payload, ensure_ascii=False)
        lines.append(f"[{event_id}] {kind}: {payload_str}")

    event_lines = "\n".join(lines)
    return _USER_TEMPLATE.format(n=len(recent), event_lines=event_lines)
