# LOOP_LOG — 자율 개발 루프 기록

> research → strategy → plan → implement(TDD) → review → commit 를 반복.
> 매 루프 1 논리 단위 = 1 커밋. 백로그는 코드리뷰(2026-07-13, feat/v2-trust-identity) 결과에서 파생.

## 백로그 (코드리뷰 발견, 우선순위순)

| ID | 심각도 | 요약 | 상태 |
|----|--------|------|------|
| C1 | CRITICAL | 타임존 skew가 decay 계산 손상 (get_conn에 SET TimeZone 없음) | ✅ Loop 1 |
| C2 | CRITICAL | honesty 승격 게이트가 decay 안 된 stale 값 사용 (whitewash 우회) | ✅ Loop 2 |
| C3 | CRITICAL | executor 정산 generic 예외 시 ROLLBACK 누락 → 커넥션 브릭 | ✅ Loop 3 |
| H1 | HIGH | 서명이 source_agent/메타데이터 미바인딩 → 결제 하이재킹 | ⬜ |
| H2 | HIGH | seller_did/payload_signature 길이 무제한 → base58 DoS | ✅ Loop 4 |
| H3 | HIGH | publish_reward=0 → 매핑 안 된 예외로 crash | ✅ Loop 6 |
| H4 | HIGH | state_changed_at이 비-전이 이벤트마다 joined_at으로 덮임 | ✅ Loop 5 |
| M1 | MEDIUM | report.py mean 미decay 표시 | ⬜ |
| M2 | MEDIUM | canary used=TRUE가 trust event 전 커밋 | ⬜ |
| M3 | MEDIUM | adjudicate_claim TOCTOU (latent) | ⬜ |
| M4 | MEDIUM | accrue_pool_fee 멱등성 가드 없음 | ⬜ |
| M5 | MEDIUM | credits from/to 인덱스 마이그레이션에서 유실 | ⬜ |
| M6 | MEDIUM | record_trust_event 50줄 초과 | ⬜ |

---

## Loop 1 — C1 타임존 skew 수정
- **research**: DuckDB Python 드라이버는 tz-aware datetime을 프로세스 로컬 TZ로 변환해 naive TIMESTAMP 저장. 호스트 KST(UTC+9)에서 +9h skew 실측.
- **strategy**: 세션 타임존을 UTC로 고정해 변환을 identity로 만든다 (icu 번들). `_aware()` 상대적 relabel 로직은 유지 — 이제 전제가 참이 됨.
- **plan**: `get_conn`에서 connect 직후 `SET TimeZone='UTC'`. 비-UTC TZ 회귀 테스트 추가.
- **implement**: `app/storage/db.py` get_conn 1줄. `tests/unit/test_storage_timezone.py` RED→GREEN.
- **review**: red(KST skew 9h)→green(0h) 확인. 전체 스위트 회귀 없음.

## Loop 2 — C2 honesty 승격 게이트 stale 값 수정
- **research**: `service.py:106`가 교차축 honesty를 decay 없이 raw로 읽음. canary 1회(obs=1.0) 후 400일 감사 공백에도 게이트가 1.0으로 통과 → member 승격(whitewash). 실측: stale=1.0, 정상 decay=0.0098.
- **strategy**: 게이트 입력 honesty를 갱신 축과 동일하게 now까지 decay. 임계 `promote_min_honesty_observations`는 감쇠 전 1.0에 보정돼 있었으므로 decay 도입 시 재보정 필요.
- **plan**: service.py에서 stored honesty decay 후 observations 사용. membership 임계 1.0→0.5("약 1 반감기(60일) 내 감사 1회"). RED: 400일 공백 승격 테스트.
- **implement**: `app/trust/service.py` 게이트 분기 + `app/trust/membership.py` 임계. `test_stale_honesty_pass_does_not_promote_after_long_gap`.
- **review**: red(member)→green(provisional). 임계 재보정으로 깨진 2개 기존 승격 테스트는 0.5로 복구(수 시간 gap→0.998>0.5). 전체 401 passed, ruff/mypy clean.

## Loop 3 — C3 executor 정산 ROLLBACK 누락
- **research**: `_charge_querier_or_fallback` Step 2가 `except InsufficientFundsError`만 롤백. 그 외 예외(InvalidAgentError 등)는 TX 열린 채 탈출 → 단일 writer 커넥션이 mid-TX로 남아 이후 BEGIN 전부 실패(서비스 브릭). 트리거: query_price=0.
- **strategy**: 다른 모든 TX 함수와 동일하게 `except Exception: ROLLBACK` 후, InsufficientFundsError만 fallback 경로, 나머지는 re-raise.
- **plan**: except 절 확장. RED: credits_transfer를 RuntimeError로 monkeypatch → 이후 BEGIN 성공 검증.
- **implement**: `app/a2a/executor.py` except 절 + `test_settlement_generic_error_rolls_back_transaction`.
- **review**: red("cannot start a transaction within a transaction")→green. 전체 402 passed, ruff/mypy clean.

## Loop 4 — H2 서명/DID 길이 상한 (base58 DoS)
- **research**: `seller_did`/`payload_signature`에 max_length 없음. `_b58decode`는 O(n^2). 200KB 입력 → ~5s 동안 단일 writer 블록. body-size 미들웨어도 없음 → 무인증 DoS.
- **strategy**: 경계(pydantic)에서 조기 거부. did:key ~56자→상한 128, sig 88자→상한 256.
- **plan**: schemas.py Field(max_length=…). RED: 100K자 필드 → ValidationError.
- **implement**: `app/api/schemas.py` 2필드. `test_publish_request_rejects_oversized_{seller_did,signature}`.
- **review**: red(통과)→green(거부). 전체 404 passed, ruff/mypy clean.

## Loop 5 — H4 state_changed_at 보존
- **research**: `service.py`가 비-전이 이벤트에서 state_changed_at을 joined_at으로 리셋 → "마지막 전이 시각"이 아니라 "최근 비-전이 이벤트 시각"을 추적하게 됨. 승격(17:00) 후 평범한 이벤트가 12:00(joined)으로 덮음. 감사 필드 손상.
- **strategy**: 전이 시 now, 미전이 시 기존 member.state_changed_at 보존.
- **plan**: upsert_membership 인자 분기. RED: 승격 후 비-전이 이벤트 → state_changed_at 보존 검증.
- **implement**: `app/trust/service.py`. `test_state_changed_at_preserved_on_non_transition`.
- **review**: red(12:00으로 덮임)→green(17:00 보존). 전체 405 passed, ruff/mypy clean.

## Loop 6 — H3 Settings 결제 하한 검증
- **research**: config에 하한 없음. publish_reward/query_price=0 → credits_transfer(amount>0) InvalidAgentError → 매핑 안 된 크래시(C3 트리거이기도).
- **strategy**: frozen dataclass `__post_init__`로 경계 조기 거부.
- **plan**: publish_reward>=1, query_price>=1 검증. RED: 0/-1 → ValueError.
- **implement**: `app/config.py` __post_init__. 신규 `tests/unit/test_config.py`.
- **review**: red(통과)→green(거부). 전체 408 passed, ruff/mypy clean.

---

## 체크포인트 (Loop 1-6 완료, 2026-07-13)
- **완료**: CRITICAL 3 (C1·C2·C3) + HIGH 3 (H2·H3·H4). 커밋 9ccd7c4→(H3).
- **전체 스위트**: 399 → 408 passed (신규 회귀 테스트 9건). ruff/mypy clean 유지.
- **남은 백로그**: H1(서명 메타데이터 바인딩 + agent_identities wiring — 암호 코어/publish 경계 다중 파일, 별도 집중 세션 권장), M1-M6.
- **다음 진입점**: H1부터. `research/agent-trust-impl-plan-2026-07.md` §P0 참조. 서명 대상에 source_agent 포함 + publish 시 등록 DID 일치 강제.
