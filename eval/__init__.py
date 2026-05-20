"""EVAL harness — pytest 비포함 (pyproject.toml norecursedirs).

수동/CI on-demand 실행:
    python eval/run_eval_1.py --mock    # 오프라인 (LLM 호출 없음)
    python eval/run_eval_1.py --live    # 실제 Anthropic Haiku 호출 (비용 발생)
"""
