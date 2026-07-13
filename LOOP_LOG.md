# LOOP_LOG — 자율 개발 루프 기록

> research → strategy → plan → implement(TDD) → review → commit 를 반복.
> 매 루프 1 논리 단위 = 1 커밋. 백로그는 코드리뷰(2026-07-13, feat/v2-trust-identity) 결과에서 파생.

## 백로그 (코드리뷰 발견, 우선순위순)

| ID | 심각도 | 요약 | 상태 |
|----|--------|------|------|
| C1 | CRITICAL | 타임존 skew가 decay 계산 손상 (get_conn에 SET TimeZone 없음) | ✅ Loop 1 |
| C2 | CRITICAL | honesty 승격 게이트가 decay 안 된 stale 값 사용 (whitewash 우회) | ✅ Loop 2 |
| C3 | CRITICAL | executor 정산 generic 예외 시 ROLLBACK 누락 → 커넥션 브릭 | ⬜ |
| H1 | HIGH | 서명이 source_agent/메타데이터 미바인딩 → 결제 하이재킹 | ⬜ |
| H2 | HIGH | seller_did/payload_signature 길이 무제한 → base58 DoS | ⬜ |
| H3 | HIGH | publish_reward=0 → 매핑 안 된 예외로 crash | ⬜ |
| H4 | HIGH | state_changed_at이 비-전이 이벤트마다 joined_at으로 덮임 | ⬜ |
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
