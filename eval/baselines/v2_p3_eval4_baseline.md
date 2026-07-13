# EVAL-4 Baseline — honesty 분리도 (v2 P3, 2026-07-13)

캡처 시점: P3 (canary 감사 + 일관성 게이트) 완료 직후.
실행: `uv run python eval/run_eval_4.py --mock` (결정적 — seed 42, 20 라운드).

## 결과: PASS

| 지표 | 값 |
|---|---|
| honest_mean (정직률 95% 판매자) | 0.875 |
| honest_lower_bound | 0.809 |
| distorter_mean (정직률 40% 판매자) | 0.106 |
| distorter_lower_bound | 0.068 |
| **separation (mean 차)** | **0.769** (기준 ≥ 0.3) |

체크: (a) separation ≥ 0.3 ✓ (b) honest lower > warn(0.4) ✓ — 정직 판매자 비제재 (c) distorter lower < warn(0.4) ✓ — 왜곡 판매자 제재 구간.

메모: 비대칭 동역학(fall ×4)으로 distorter의 mean이 명목 정직률(0.40)보다
훨씬 낮게 수렴 — 의도된 설계 (배신은 비싸다). 파라미터 변경
(fall_multiplier, prior, warn 임계) 시 이 baseline 재캡처.
