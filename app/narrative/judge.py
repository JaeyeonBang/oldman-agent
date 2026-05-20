"""LLM 인용 근거 판정자 — Phase 4.0.

주어진 주장 문장(claim)과 이벤트 페이로드(event_payload)를 바탕으로
LLM judge가 인용이 근거 있는지(is_grounded) 판정한다.

⚠️ 이 파일은 CLAUDE.md EVAL 트리거 대상. 변경 시 EVAL-2 재실행 필요.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.llm.base import LLMRequest, LLMTier

_LOG = logging.getLogger(__name__)

JUDGE_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "judge_grounding.md"

# JSON 블록 추출용 정규식 (가장 바깥 { } 매칭)
_JSON_EXTRACT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


@dataclass(frozen=True)
class JudgeVerdict:
    """judge_grounding 반환값 (불변)."""

    is_grounded: bool
    reason: str


_CODE_FENCE_RE = re.compile(
    r"^```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL,
)


def _strip_fences(text: str) -> str:
    """v1.0.5: ```json ... ``` 같은 markdown 코드 펜스 제거."""
    stripped = text.strip()
    m = _CODE_FENCE_RE.match(stripped)
    return m.group(1).strip() if m else stripped


def parse_judge_output(text: str) -> JudgeVerdict:
    """LLM 출력 텍스트에서 JudgeVerdict를 파싱한다.

    파싱 전략:
    0. v1.0.5: markdown 코드 펜스 제거 — DeepSeek 등이 JSON을 펜스로 감싸 응답.
    1. 텍스트 전체를 ``json.loads`` 시도 (nested object 안전).
    2. 실패 시 정규식으로 첫 ``{ ... }`` 블록 추출 후 파싱.

    실패 시 ``JudgeVerdict(False, "parse_error")``.
    """
    text = _strip_fences(text)  # v1.0.5
    data: Any = None
    # 1차: 전체 텍스트를 JSON으로 시도
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict):
            data = candidate
    except json.JSONDecodeError:
        pass

    # 2차: 정규식으로 첫 { ... } 블록 추출 (LLM이 프로즈로 감싼 경우)
    if data is None:
        match = _JSON_EXTRACT_RE.search(text)
        if match is None:
            _LOG.warning("judge: JSON 블록 추출 실패: %r", text[:200])
            return JudgeVerdict(is_grounded=False, reason="parse_error")
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            _LOG.warning("judge: JSON 파싱 실패: %s | text=%r", exc, text[:200])
            return JudgeVerdict(is_grounded=False, reason="parse_error")
        if not isinstance(data, dict):
            _LOG.warning("judge: JSON이 dict가 아님: %r", data)
            return JudgeVerdict(is_grounded=False, reason="parse_error")

    is_grounded = bool(data.get("is_grounded", False))
    reason_value = data.get("reason", "")
    # reason이 dict/list인 경우 직렬화 (이전 버전은 silent str(dict))
    if isinstance(reason_value, (dict, list)):
        reason_value = json.dumps(reason_value, ensure_ascii=False)
    reason = str(reason_value)
    return JudgeVerdict(is_grounded=is_grounded, reason=reason)


async def judge_grounding(
    provider: Any,
    claim: str,
    event_payload: dict[str, Any],
) -> JudgeVerdict:
    """LLM provider를 호출하여 인용 근거를 판정한다.

    Args:
        provider: LLMProvider 호환 객체 (CannedJudge 또는 AnthropicProvider).
        claim: 판정 대상 주장 문장 (인용 마커 포함 가능).
        event_payload: 인용 마커가 가리키는 이벤트의 payload dict.

    Returns:
        JudgeVerdict — provider 예외 시 ``JudgeVerdict(False, "provider_error")``.
    """
    # 시스템 프롬프트 로드
    try:
        system_prompt = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        _LOG.error("judge: 프롬프트 파일 로드 실패: %s", exc)
        return JudgeVerdict(is_grounded=False, reason="provider_error")

    payload_json = json.dumps(event_payload, ensure_ascii=False, indent=2)
    user_message = (
        f"주장 문장:\n{claim}\n\n"
        f"이벤트 페이로드:\n{payload_json}"
    )

    try:
        response = await provider.complete(
            LLMRequest(
                system=system_prompt,
                prompt=user_message,
                tier=LLMTier.CHEAP,
                max_tokens=256,
            )
        )
    except Exception as exc:
        _LOG.warning("judge: provider 호출 실패: %s", exc)
        return JudgeVerdict(is_grounded=False, reason="provider_error")

    return parse_judge_output(response.text)
