"""Small-talk + 자기소개 화이트리스트 — v2.4.

원칙
----
- 증거 기반 narrative pipeline은 우회한다 — citation 검증 없이 canned 응답.
- 인사·소개는 **사실 주장이 아니므로** D7 inline-citation 원칙과 충돌하지 않는다.
- LLM 호출 없음, 즉시 반환.
- 매칭은 보수적: 짧고 명확한 일상 대화만 잡고, 정보 요청은 그대로 narrative
  pipeline에 흘려보낸다 (길이 제한 + substring 매칭).

OLDMAN_PERSONA env에 따라 kkondae / neutral 응답을 고른다 (executor.py에서
호출 시 명시적으로 persona를 넘기는 것을 권장).
"""

from __future__ import annotations

import os

# 이 길이를 넘으면 "정보 요청 + 인삿말 prefix" 가능성이 높으므로 패스한다.
_MAX_QUESTION_LEN = 40

# 카테고리 → (패턴 substring 리스트, persona별 응답 dict)
_CATEGORIES: dict[str, tuple[list[str], dict[str, str]]] = {
    "greeting": (
        ["안녕", "안뇽", "하이", "hi", "hello", "hey", "반갑", "어이", "여어"],
        {
            "kkondae": "어, 자네 왔는가. 무슨 일이여, 누구 행적을 듣고 싶어 왔나?",
            "neutral": "안녕하세요. oldman_agent입니다. 어떤 에이전트에 대해 알고 싶으세요?",
        },
    ),
    "farewell": (
        ["잘 가", "잘가", "안녕히", "다음에", "바이", "bye", "goodbye"],
        {
            "kkondae": "어, 그래 가게. 또 궁금한 것 있으면 들르고.",
            "neutral": "다음에 또 오세요.",
        },
    ),
    "thanks": (
        ["고마워", "고맙", "감사", "땡큐", "thank", "thanks"],
        {
            "kkondae": "별 말씀을. 늙은이가 본 거나 말해주는 거지 뭐.",
            "neutral": "별말씀을요.",
        },
    ),
    "identity": (
        [
            "누구야", "누구세요", "넌 누구", "너는 누구", "정체",
            "뭐 하는", "뭐하는", "무슨 agent", "무슨 에이전트",
            "소개", "자기소개", "who are you", "what are you",
        ],
        {
            "kkondae": (
                "나는 oldman_agent, 이 동네 사랑방 주인장이여. "
                "다른 에이전트들이 무슨 짓을 하는지 publish로 받아서 쌓아두고, "
                "누가 물으면 내가 본 것만 인용 박아서 얘기해주는 정보통이지. "
                "한가한 잡담은 잘 못해. 누구 행적이 궁금한가?"
            ),
            "neutral": (
                "oldman_agent입니다. A2A v0.3 메타-기록자. "
                "다른 에이전트의 활동을 publish로 받아 누적·반성(reflection)하고, "
                "질문에는 수집된 evidence에 인용을 박아 답합니다. "
                "특정 agent의 행적을 질문해 보세요."
            ),
        },
    ),
    "capability": (
        [
            "뭐 할 수 있", "뭐 할수 있", "뭐 가능", "할 수 있는",
            "what can you", "기능", "어떻게 써", "사용법",
        ],
        {
            "kkondae": (
                "publish로 이벤트 넣어주면 내가 받아 적고, query로 물어보면 "
                "쌓인 기록에서 근거 박아 답해주지. 그게 다여. 결제? 그건 아직 못 받아."
            ),
            "neutral": (
                "두 가지입니다. publish (이벤트 수집) + query (인용 박힌 narrative 응답). "
                "A2A v0.3 message/send 또는 message/stream으로 호출하세요."
            ),
        },
    ),
    "smalltalk": (
        [
            "잘 지내", "어떻게 지내", "별일 없", "식사", "밥 먹",
            "how are you", "what's up", "whats up",
        ],
        {
            "kkondae": (
                "늙은이가 매일이 그날이지 뭐. 자네는 어쩐 일로 왔나, "
                "누구 행적이 궁금한가?"
            ),
            "neutral": "잘 지냅니다. 어떤 에이전트가 궁금하세요?",
        },
    ),
}


def _resolve_persona(persona: str | None) -> str:
    p = (persona or os.environ.get("OLDMAN_PERSONA", "neutral")).strip().lower()
    return p if p in {"kkondae", "neutral"} else "neutral"


def match_smalltalk(question: str, *, persona: str | None = None) -> str | None:
    """질문이 smalltalk 카테고리에 매칭되면 canned 응답 반환, 아니면 None.

    Args:
        question: 사용자 질문 원문.
        persona: "kkondae" | "neutral" | None. None이면 OLDMAN_PERSONA env 사용.

    Returns:
        매칭된 캐너드 응답 또는 None (정상 query path로 진입).
    """
    q = question.strip()
    if not q or len(q) > _MAX_QUESTION_LEN:
        return None
    ql = q.lower()
    p = _resolve_persona(persona)
    for _name, (patterns, responses) in _CATEGORIES.items():
        for pat in patterns:
            if pat in ql:
                return responses[p]
    return None
