# A2A SDK Pub/Sub Spike — 2026-05-20

## 검색 방법

- PyPI 검색: `a2a-sdk`, `python-a2a`, `pya2a`, `a2a-protocol`
- GitHub 이슈 검색: `a2aproject/A2A` pub/sub 관련 이슈 #1029, #1593
- 공식 SDK README + streaming 문서 확인

## 발견 내용

### 패키지 존재 여부 — YES

공식 SDK `a2a-sdk` (v1.0.3, 2026-05-13 릴리즈)가 PyPI에 존재함.
GitHub: `a2aproject/a2a-python`

### 스트리밍 — 존재 (SSE 기반)

`a2a-sdk` v1.0은 **SSE(Server-Sent Events) 스트리밍**을 지원함:
- `AgentExecutor`가 두 가지 패턴을 따름:
  1. Message-only stream
  2. Task lifecycle stream (`TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`)
- 이것은 **단방향 server→client push**이며, broker 없는 HTTP long-poll 방식임.

### 네이티브 Pub/Sub — NO (오픈 이슈)

- GitHub 이슈 #1029: "Support publish/subscribe methods for async communications" — **아직 미구현**
- GitHub 이슈 #1593: "Built-in Pub/Sub support in the A2A protocol" — **feature request 단계**
- 현재 A2A RPC 메서드는 **point-to-point**만 지원. 브로커 기반 pub/sub 없음.
- Redis 기반 써드파티 확장(`a2a-redis`)이 `RedisPubSubEventQueue`를 제공하지만, 이는 공식 프로토콜 외부 레이어임.

## 결론 / Verdict

**HTTP-only continuation** — M2는 현재 설계대로 `POST /publish` HTTP 엔드포인트 유지.

A2A SDK의 네이티브 pub/sub은 아직 feature request 단계이므로 oldman_agent가 의존하기 부적합.
SSE 스트리밍은 `/query` 응답 스트리밍에 M3+에서 고려 가능.

## M3 진입점 권고

- `a2a-sdk` v1.0 SSE 스트리밍을 `/query` 엔드포인트에 적용 검토 (M3)
- Redis-backed pub/sub (`a2a-redis`)은 에이전트 수 50+ 스케일 시점에 재검토 (v1.5+)
- `a2a-sdk` 자체를 M3에서 설치해 `AgentCard` 타입 채택 검토 (현재는 수동 구현)
