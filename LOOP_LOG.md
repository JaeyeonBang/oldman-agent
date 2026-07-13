# LOOP_LOG — 자율 개발 루프 기록

> research → strategy → plan → implement(TDD) → review → commit 를 반복.
> 매 루프 1 논리 단위 = 1 커밋. 백로그는 코드리뷰(2026-07-13, feat/v2-trust-identity) 결과에서 파생.

## 백로그 (코드리뷰 발견, 우선순위순)

| ID | 심각도 | 요약 | 상태 |
|----|--------|------|------|
| C1 | CRITICAL | 타임존 skew가 decay 계산 손상 (get_conn에 SET TimeZone 없음) | ✅ Loop 1 |
| C2 | CRITICAL | honesty 승격 게이트가 decay 안 된 stale 값 사용 (whitewash 우회) | ✅ Loop 2 |
| C3 | CRITICAL | executor 정산 generic 예외 시 ROLLBACK 누락 → 커넥션 브릭 | ✅ Loop 3 |
| H1 | HIGH | 서명이 source_agent/메타데이터 미바인딩 → 결제 하이재킹 | ✅ Loop 7 (Part 1) |
| H1b | HIGH | agent_identities 등록/강제 wiring (TOFU) | ✅ Loop 15 |
| H2 | HIGH | seller_did/payload_signature 길이 무제한 → base58 DoS | ✅ Loop 4 |
| H3 | HIGH | publish_reward=0 → 매핑 안 된 예외로 crash | ✅ Loop 6 |
| H4 | HIGH | state_changed_at이 비-전이 이벤트마다 joined_at으로 덮임 | ✅ Loop 5 |
| M1 | MEDIUM | report.py mean 미decay 표시 | ✅ Loop 9 |
| M2 | MEDIUM | canary used=TRUE가 trust event 전 커밋 | ✅ Loop 10 |
| M3 | MEDIUM | adjudicate_claim TOCTOU (latent) | ✅ Loop 11 |
| M4 | MEDIUM | accrue_pool_fee 멱등성 가드 없음 | ✅ Loop 12 |
| M5 | MEDIUM | credits from/to 인덱스 마이그레이션에서 유실 | ✅ Loop 8 |
| M6 | MEDIUM | record_trust_event 50줄 초과 | ✅ Loop 13 |

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

## Loop 7 — H1 서명 source_agent 바인딩 (Part 1)
- **research**: `_message(payload)`가 payload만 서명 → 서명이 '무엇을'만 증명, '누가 파는가'(source_agent=결제 수취자)는 미증명. 캡처된 (did, payload, sig)를 공격자가 source_agent=carol로 먼저 제출(payload_hash 전역 UNIQUE 레이스) → 결제·평판 하이재킹.
- **strategy**: 서명 대상에 source_agent 바인딩(`<payload_hash>|<NFC(source_agent)>`). 해시 고정 길이(64hex)라 구분자 결합 모호성 없음. sign/verify에 source_agent 필수 인자 → 미바인딩 서명 원천 차단.
- **plan**: identity.py `_signing_message` + sign/verify 시그니처. publish.py verify에 req.source_agent. 전 호출처(테스트 3파일+village_demo) 갱신. RED: carol 재제출 → InvalidSignatureError.
- **implement**: `app/trust/identity.py`, `app/api/publish.py`, 호출처 5곳. hijack 테스트(publish 레벨) + source_agent 바인딩 테스트(unit).
- **review**: red(TypeError→하이재킹 통과)→green(거부). 전체 410 passed, ruff/mypy clean, village_demo 완주(Σ400==Σ400).
- **후속 H1b**: `agent_identities`(source_agent↔DID) 등록/강제는 등록 flow 부재 → 별도 백로그. Part 1만으로 하이재킹은 완전 차단(서명 위조 불가).

## Loop 8 — M5 credits from/to 인덱스 복구
- **research**: 002가 만든 idx_credits_tx_from/to가 006·008 테이블 재생성(DROP+RENAME)에서 소멸, 재생성 안 됨. 실측: 마이그레이션 후 credits_transactions 인덱스는 idx_credits_tx_ts만 생존. from_agent GROUP/필터 쿼리(audit·admin) full scan.
- **strategy**: 기존 마이그레이션은 이미 적용돼 재실행 안 되므로 신규 마이그레이션 009로 IF NOT EXISTS 복구.
- **plan**: 009_credits_indexes.sql. RED: apply_migrations 후 두 인덱스 존재 검증.
- **implement**: `app/storage/migrations/009_credits_indexes.sql`. test_db.py 회귀.
- **review**: red({idx_credits_tx_ts}만)→green(from/to 존재). 전체 411 passed.

## Loop 9 — M1 report 표시 점수 decay
- **research**: `report.py:85`가 stored[0].mean을 decay 없이 표시 → 1년 전 고득점 판매자가 여전히 "열에 8쯤"으로 서술(C1/ledger 전제 위반).
- **strategy**: build_reputation_report에 now 옵션 추가, 표시 전 각 축 점수를 now까지 decay. 기본값=실제 시각이라 executor 호출부 무변경.
- **plan**: report.py now 파라미터 + decay. RED: fresh vs 400일 stale 리포트 digit 비교.
- **implement**: `app/trust/report.py`. test_trust_report 회귀.
- **review**: red(now 인자 부재)→green(stale digit < fresh digit). 전체 412 passed, ruff/mypy clean.

## Loop 10 — M2 canary 소모 순서
- **research**: `canary.py`가 used=TRUE(autocommit)를 record_trust_event 전에 커밋 → 후자 실패 시 canary만 소모되고 honesty 신호 유실 + 재감사 불가.
- **strategy**: 순서 반대로 — honesty 기록 성공 후에만 canary 소모. 실패 시 raise로 used=FALSE 유지.
- **plan**: judge_canary_response 두 문장 순서 교체. RED: record_trust_event monkeypatch로 실패 → used 미소모 검증.
- **implement**: `app/trust/canary.py`. test_trust_canary 회귀.
- **review**: red(used=True 소모)→green(used=False). 전체 413 passed, ruff/mypy clean.

## Loop 11 — M3 adjudicate_claim 레이스 가드
- **research**: pre-check(SELECT status)와 UPDATE 사이 가드 부재. 두 동시 판정이 pre-check 통과 후 둘 다 UPDATE→이중 배상(sync route threadpool에서 실동시성). latent(현재 미wiring).
- **strategy**: invoices.mark_invoice_settled 패턴 차용 — UPDATE에 AND status='pending' + RETURNING, 패자는 raise→rollback.
- **plan**: 승인/거부 UPDATE 둘 다 가드. RED: credits_transfer monkeypatch로 UPDATE 직전 status 변경 재현 → ClaimError 기대.
- **implement**: `app/trust/refund_pool.py`. test 회귀.
- **review**: red(DID NOT RAISE)→green(ClaimError). 전체 414 passed, ruff/mypy clean.

## Loop 12 — M4 accrue_pool_fee 멱등성
- **research**: invoice당 pool_fee 중복 방지 가드 없음. 현재 1회 호출(non-live)이나 retry 경로 추가 시 이중 적립.
- **strategy**: TX 내 존재 검사 — 같은 invoice의 pool_fee(applied)가 있으면 no-op.
- **plan**: SELECT 1 가드. RED: 같은 invoice 2회 적립 → 잔고 +fee 1회만.
- **implement**: `app/trust/refund_pool.py`. test 회귀.
- **review**: red(grant+2)→green(grant+1). 전체 415 passed, ruff/mypy clean.

## Loop 13 — M6 record_trust_event 복잡도 분리 (리팩터)
- **research**: record_trust_event가 membership 조회+점수 decay/update+honesty 교차읽기+전이+3-write를 한 함수에 담아 프로젝트 50줄 가이드 초과.
- **strategy**: 순수 read-only 계산 2개(_decayed_updated_score, _honesty_gate_observations)를 명명 헬퍼로 추출. 동작 보존이라 신규 테스트 없이 기존 415 스위트가 회귀 가드(Red-Green의 IMPROVE 단계).
- **implement**: `app/trust/service.py` 헬퍼 2개 + 본문 슬림화. 남은 길이는 orchestration의 kwarg-per-line 포맷.
- **review**: 전체 415 passed(동작 불변), ruff/mypy clean.

---

## 체크포인트 2 (Loop 1-13 완료, 2026-07-13)
- **완료**: CRITICAL 3 (C1-C3) + HIGH 4 (H1-H4) + MEDIUM 6 (M1-M6). 커밋 13개.
- **전체 스위트**: 399 → 415 passed (신규 회귀 16건). ruff/mypy clean 유지. village_demo 완주.
- **남은 백로그**: H1b(agent_identities 등록/강제 — 등록 flow 설계 필요). LOW 3(L1 정책결정/L2 마이그레이션 TX/L3 admin 상수시간 비교)는 선택.
- **다음 진입점**: H1b (등록 flow 설계 필요).

## Loop 14 — L3 admin 토큰 상수시간 비교
- **research**: `_check_token`이 `provided != expected` 평문 비교 → 첫 불일치 바이트 단락으로 타이밍 사이드채널. /admin/trust가 평판 내부 노출이라 토큰 load-bearing.
- **strategy**: hmac.compare_digest로 상수시간화. 동작 동일(기존 토큰 가드 테스트가 가드).
- **implement**: `app/api/admin.py` import hmac + 비교 교체.
- **review**: 기존 admin 토큰 테스트 4개 통과(401/200 불변), 전체 415 passed, ruff/mypy clean.

- **남은 것**: H1b(agent_identities 등록/강제 — 등록 flow 설계 필요), L1(정책 결정: jaccard 오탐→영구 축출 검토), L2(마이그레이션 명시 TX wrap, 데모 수준 허용).

## Loop 15 — H1b agent_identities TOFU 등록/강제
- **research**: `storage/identities.py`(upsert/get_agent_identity)가 dead code. publish가 source_agent↔DID 바인딩을 강제하지 않아, 한 source_agent가 매 요청 다른 DID를 쓰거나 두 이름이 같은 DID를 쓸 수 있었다.
- **strategy**: TOFU(Trust On First Use) — 최초 서명 publish에서 source_agent↔DID 등록, 이후 다른 DID면 DidMismatchError로 거부. 등록 엔드포인트 없이 기존 publish 경로에 얹어 데모 친화.
- **plan**: DidMismatchError(PublishError) 추가. 서명 검증 통과 후 get→없으면 upsert, 있으면 일치 검증. RED: 등록 확인 + 다른 DID 거부.
- **implement**: `app/api/publish.py` 예외 + wiring. test_publish_signed 회귀 2건.
- **review**: red(등록 안 됨/미거부)→green. 전체 417 passed, ruff/mypy clean, village_demo 완주.

---

## 체크포인트 3 (Loop 1-15 완료, 2026-07-13)
- **완료**: CRITICAL 3 + HIGH 4 + H1b + MEDIUM 6 + LOW 1(L3) = 15 커밋.
- **전체 스위트**: 399 → 417 passed (신규 회귀 18건). ruff/mypy clean, village_demo 완주.
- **남은 것(선택)**: L1(정책 판단), L2(마이그레이션 TX wrap, 데모 허용). 코드리뷰 실행 백로그는 전부 소진.

## Loop 16 — L2 마이그레이션 원자성
- **research**: apply_migrations가 conn.execute(sql) 후 버전 기록 — DuckDB는 문장별 autocommit이라 다중문 마이그레이션 중간 실패 시 부분 반영 + 버전 미기록으로 스키마 분기. 실측: 실패 마이그레이션의 zzz_partial 테이블이 남음.
- **strategy**: 마이그레이션 SQL + 버전 기록을 한 BEGIN/COMMIT으로 원자화, 실패 시 ROLLBACK.
- **plan**: apply_migrations 루프에 TX wrap. RED: 실패 마이그레이션 주입 → 부분 테이블 없음 + 버전 미기록.
- **implement**: `app/storage/db.py`. test_db 회귀.
- **review**: red(zzz_partial 잔존)→green(롤백). 전체 418 passed(기존 006/008 DROP+RENAME도 TX 내 정상), ruff/mypy clean.

## 최종 (Loop 1-16, 2026-07-13)
- **완료**: CRITICAL 3 + HIGH 4 + H1b + MEDIUM 6 + LOW 2(L2·L3) = 16 커밋. 코드리뷰 실행 가능 항목 전부 소진.
- **전체 스위트**: 399 → 418 passed (신규 회귀 19건). ruff/mypy clean, village_demo 완주.
- **남은 것**: L1(product 정책 결정 — jaccard 오탐→영구 축출이 의도인지 사용자 판단 필요, 코드 변경 아님).

## Loop 17 — L1 canary blunt-heuristic caveat (docstring)
- **research**: 리뷰어 L1(LOW)은 정책 변경이 아니라 문서 갭 — probe.py는 jaccard 한계를 자기문서화하는데 canary.py엔 없음. 오탐(정직한 의역→canary_fail→영구 회복바 손상) 위험을 명시하라는 요청.
- **strategy**: canary.py docstring에 한계 caveat 추가 + 정책 판단(엄격 유지 vs semantic judge/사면)이 product 결정임을 명시. 동작 무변경.
- **implement**: `app/trust/canary.py` docstring only.
- **review**: ruff clean, 전체 418 passed(불변), EVAL-4 separation 0.769 PASS(baseline 유지 — docstring이 결정적 eval에 무영향 실증).
- **결과**: 코드리뷰 전 severity(C/H/M/L) 백로그 완전 종결. 큰 정책 변경(semantic judge/사면)은 여전히 별도 product 사이클.
