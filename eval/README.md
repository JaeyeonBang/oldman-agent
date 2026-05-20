# EVAL-1 — Reflection Accuracy Harness

## 실행

```bash
# 오프라인 (캐닝된 응답, 비용 0)
python eval/run_eval_1.py --mock

# 실제 Anthropic Haiku 호출 (비용 발생, ANTHROPIC_API_KEY 필요)
export ANTHROPIC_API_KEY=sk-ant-xxx
python eval/run_eval_1.py --live
```

## 측정 지표

각 골든 케이스에 대해:
- expected_descriptors (사람이 큐레이션한 정답 키워드 집합)
- generated_descriptors (LLM이 생성한 키워드 집합)
- jaccard(generated, expected) ∈ [0, 1]

전체 평균(mean jaccard)을 보고하며, M2 baseline pass threshold는 **0.6**.

## 골든 셋

- `golden_sets/reflection_baseline.json` — v1, 5개 케이스 (agent×3, pair×1, society×1)
- 각 케이스는 `mock_response` 필드를 가지며 `--mock` 모드에서 사용됨
- `expected_descriptors`는 사람 큐레이션 (M2 ship 시점 캡처)

## 비용 추정 (--live)

- 5 cases × 약 2K input tokens (system + user) × 200 output tokens
- Claude Haiku 4.5 단가 (2026-05 기준): $0.80/1M input, $4.00/1M output
- 예상 비용: ~$0.02 / run (캐시 미적중 시). 프롬프트 캐시 적중 시 절반 이하.

## CI 권고

`--mock` 만 CI에서 자동 실행. `--live`는 M2 ship 시점과 prompt 변경 시 수동.
