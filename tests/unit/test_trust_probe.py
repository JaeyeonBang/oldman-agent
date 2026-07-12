"""P3 — paraphrase 일관성 게이트 (TDD).

고액 매입 전, 같은 질문을 바꿔 물어 답의 합치도를 측정 — 낮은 합치도는
조작/헛소리 신호 (semantic-entropy의 결정적 근사: tokenize+pairwise jaccard).
LLM 판정이 아니라서 mock 모드에서도 동일하게 동작한다.
"""

from __future__ import annotations

import pytest

from app.trust.probe import check_consistency


def test_consistent_answers_pass() -> None:
    verdict = check_consistency(
        [
            {"text": "김봇이 이봇에게 데이터셋을 공유했다"},
            {"text": "김봇이 이봇에게 데이터셋을 공유했다"},
            {"text": "이봇에게 김봇이 데이터셋을 공유했다"},  # 어순만 다름
        ]
    )
    assert verdict.passed is True
    assert verdict.score > 0.9


def test_inconsistent_answers_fail() -> None:
    verdict = check_consistency(
        [
            {"text": "김봇이 이봇에게 데이터셋을 공유했다"},
            {"text": "박봇은 어제 서버를 내렸다"},
            {"text": "날씨가 좋아서 산책했다"},
        ]
    )
    assert verdict.passed is False
    assert verdict.score < 0.3


def test_threshold_is_configurable() -> None:
    answers = [
        {"text": "김봇이 데이터셋을 공유했다"},
        {"text": "김봇이 데이터셋을 이봇과 공유했다"},
    ]
    strict = check_consistency(answers, threshold=0.99)
    lenient = check_consistency(answers, threshold=0.5)
    assert strict.passed is False
    assert lenient.passed is True


def test_requires_at_least_two_answers() -> None:
    with pytest.raises(ValueError):
        check_consistency([{"text": "혼자"}])
