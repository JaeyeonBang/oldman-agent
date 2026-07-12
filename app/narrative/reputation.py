"""평판 narrative LLM 렌더링 — template v0 위의 페르소나 레이어 (P4 마무리).

안전 설계 (EVAL-2 원칙 유지):
  - citations가 없으면 LLM을 호출하지 않는다 (미지 에이전트 응답은 결정적).
  - LLM 출력의 모든 ``[↑xxxx]`` 마커는 report.citations의 short_id 집합에
    속해야 한다 — 발명된 마커 발견 시 **template로 fallback** (hallucinated
    citation이 유료 응답에 나가는 일이 구조적으로 불가능).
  - provider 예외도 fallback. 응답은 항상 나간다.

프롬프트: prompts/reputation_{persona}.md (OLDMAN_PERSONA 토글 — 기존
narrative 프롬프트와 동일 규약). 이 파일과 프롬프트 변경은 CLAUDE.md의
EVAL 트리거 대상 (EVAL-2/3 재실행).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.llm.base import LLMRequest, LLMTier
from app.trust.report import ReputationReport

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
_PERSONA_FILE_MAP: dict[str, Path] = {
    "neutral": _PROMPTS_DIR / "reputation_neutral.md",
    "kkondae": _PROMPTS_DIR / "reputation_kkondae.md",
}
_MARKER_RE = re.compile(r"\[↑([^\]]+)\]")


def load_reputation_prompt(persona: str | None = None) -> str:
    p = persona or os.environ.get("OLDMAN_PERSONA", "neutral")
    if p not in _PERSONA_FILE_MAP:
        raise ValueError(f"unknown persona '{p}'; valid: {list(_PERSONA_FILE_MAP)}")
    return _PERSONA_FILE_MAP[p].read_text(encoding="utf-8")


def _facts_payload(report: ReputationReport) -> str:
    return json.dumps(
        {
            "subject_agent": report.subject_agent,
            "state": report.state,
            "violation_count": report.violation_count,
            "citations": [
                {"marker": f"[↑{c.short_id}]", "cause": c.cause}
                for c in report.citations
            ],
        },
        ensure_ascii=False,
    )


def _markers_valid(text: str, report: ReputationReport) -> bool:
    """출력 마커 ⊆ 허용 short_id, 그리고 (citations 존재 시) 최소 1개 사용."""
    found = _MARKER_RE.findall(text)
    allowed = {c.short_id for c in report.citations}
    if report.citations and not found:
        return False
    return all(m in allowed for m in found)


async def render_reputation_narrative(
    provider: Any,
    report: ReputationReport,
    *,
    persona: str | None = None,
) -> tuple[str, bool]:
    """(text, used_llm). LLM 실패/검증 실패 시 template text로 fallback."""
    if provider is None or not report.citations:
        return report.text, False
    try:
        resp = await provider.complete(
            LLMRequest(
                system=load_reputation_prompt(persona),
                prompt=_facts_payload(report),
                tier=LLMTier.CHEAP,
                max_tokens=512,
                metadata={"purpose": "reputation_narrative"},
            )
        )
        text = resp.text.strip()
    except Exception:
        return report.text, False
    if not text or not _markers_valid(text, report):
        return report.text, False
    return text, True
