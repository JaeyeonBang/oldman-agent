"""평판 리포트 빌더 — ``oldman.intent=reputation``의 코어 (P4).

포지셔닝 (devil's advocate C2 반영): 꼰대의 평판 발화는 정본 점수가 아니라
**주관적 labeler의 판단**이다 — "내가 보기엔"으로 시작하고, 모든 주장에
trust_events citation을 단다 (판단의 재현 가능성 = 점수의 citation).

template v0: 결정적 문자열 조립. LLM renderer(꼰대 페르소나 프롬프트) 통합은
EVAL-2/3 재실행과 함께 후속 — prompts/renderer 미접촉으로 기존 EVAL 보존.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from app.storage.trust import get_membership, get_trust_score
from app.trust.membership import MembershipState

_STATE_VERDICTS: dict[MembershipState, str] = {
    "provisional": "아직 잘 모르는 축이야. 몇 번 더 겪어봐야 알지",
    "member": "제법 믿을 만한 축이야. 거래도 꼬박꼬박, 말도 여태 어긋난 적 없네",
    "warned": "요즘 하는 말이 영 수상쩍어. 나 같으면 반만 믿겠네",
    "penalized": "그놈 말은 값을 못 쳐줘. 몇 번을 어긋났는지 아는가",
    "excluded": "사랑방에서 내쫓은 놈이야. 상종을 말게",
}


@dataclass(frozen=True)
class ReportCitation:
    short_id: str
    trust_event_id: str
    cause: str


@dataclass(frozen=True)
class ReputationReport:
    subject_agent: str
    state: MembershipState
    violation_count: int
    text: str
    citations: list[ReportCitation] = field(default_factory=list)


def build_reputation_report(
    conn: duckdb.DuckDBPyConnection,
    *,
    subject_agent: str,
    max_citations: int = 5,
) -> ReputationReport:
    member = get_membership(conn, subject_agent)
    if member is None:
        text = (
            f"{subject_agent}? 글쎄, 나로선 모르는 이름일세. "
            "우리 사랑방엔 온 적이 없는 놈이야. 미덥고 말고 할 것도 없지."
        )
        return ReputationReport(
            subject_agent=subject_agent,
            state="provisional",
            violation_count=0,
            text=text,
            citations=[],
        )

    rows = conn.execute(
        "SELECT trust_event_id, cause FROM trust_events "
        "WHERE agent_id = ? ORDER BY ts DESC LIMIT ?",
        [subject_agent, max_citations],
    ).fetchall()
    citations = [
        ReportCitation(
            short_id=str(r[0])[:8], trust_event_id=str(r[0]), cause=r[1]
        )
        for r in rows
    ]
    markers = " ".join(f"[↑{c.short_id}]" for c in citations)

    parts = [
        f"내가 보기엔 {subject_agent} 그놈은 {_STATE_VERDICTS[member.state]}."
    ]
    scores = []
    for criterion, label in (("reliability", "거래는"), ("honesty", "말은")):
        stored = get_trust_score(conn, subject_agent, criterion)
        if stored is not None:
            scores.append(f"{label} 열에 {round(stored[0].mean * 10)}쯤 믿네")
    if scores:
        parts.append(", ".join(scores) + ".")
    if member.violation_count > 0:
        parts.append(f"어긋난 게 벌써 {member.violation_count}번이야.")
    if markers:
        parts.append(f"근거를 대자면 이렇네: {markers}.")
    parts.append("어디까지나 이 늙은이 소견일세 — 딴 사랑방 얘기도 들어보게.")

    return ReputationReport(
        subject_agent=subject_agent,
        state=member.state,
        violation_count=member.violation_count,
        text=" ".join(parts),
        citations=citations,
    )
