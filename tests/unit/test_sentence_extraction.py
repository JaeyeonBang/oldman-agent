"""Phase 4.1 — RED tests: extract_sentence_for_marker."""

from __future__ import annotations


class TestExtractSentenceForMarker:
    def test_extract_sentence_simple_period_split(self) -> None:
        from app.narrative.sentences import extract_sentence_for_marker

        text = "첫 문장입니다. agent_alice가 행동했습니다 [↑e1a2b3c4]. 세 번째 문장입니다."
        result = extract_sentence_for_marker(text, "[↑e1a2b3c4]")
        assert result is not None
        assert "[↑e1a2b3c4]" in result
        assert "agent_alice" in result
        # 다른 문장이 포함되지 않아야 함
        assert "첫 문장" not in result
        assert "세 번째" not in result

    def test_extract_sentence_marker_at_start(self) -> None:
        from app.narrative.sentences import extract_sentence_for_marker

        text = "[↑eabcdef01] 이 문장이 첫 번째입니다. 두 번째 문장입니다."
        result = extract_sentence_for_marker(text, "[↑eabcdef01]")
        assert result is not None
        assert "[↑eabcdef01]" in result

    def test_extract_sentence_marker_at_end(self) -> None:
        from app.narrative.sentences import extract_sentence_for_marker

        text = "첫 문장입니다. 마지막 문장에 마커가 있습니다 [↑e99887766]"
        result = extract_sentence_for_marker(text, "[↑e99887766]")
        assert result is not None
        assert "[↑e99887766]" in result
        assert "마지막 문장" in result

    def test_extract_sentence_marker_absent_returns_none(self) -> None:
        from app.narrative.sentences import extract_sentence_for_marker

        text = "마커가 없는 텍스트입니다. 이것도 마찬가지입니다."
        result = extract_sentence_for_marker(text, "[↑edeadbeef]")
        assert result is None

    def test_extract_sentence_korean_punctuation(self) -> None:
        from app.narrative.sentences import extract_sentence_for_marker

        text = "에이전트가 보고했어요. agent_bob이 탐지했습니다 [↑e11223344]. 다음 문장이에요."
        result = extract_sentence_for_marker(text, "[↑e11223344]")
        assert result is not None
        assert "agent_bob" in result
        assert "[↑e11223344]" in result

    def test_extract_sentence_no_punctuation_returns_full_text(self) -> None:
        from app.narrative.sentences import extract_sentence_for_marker

        text = "구두점 없이 [↑eaabbccdd] 마커만 있는 텍스트"
        result = extract_sentence_for_marker(text, "[↑eaabbccdd]")
        # 문장 구분이 없으면 전체 텍스트를 반환해야 함
        assert result is not None
        assert result == text
