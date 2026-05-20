"""Phase 3.2 — RED tests: narrative prompt loader and user message builder."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


class TestLoadNarrativePrompt:
    def test_load_narrative_prompt_returns_non_empty(self) -> None:
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt()
        assert isinstance(text, str)
        assert len(text) > 100

    def test_load_narrative_prompt_contains_citation_contract(self) -> None:
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt()
        # 인용 마커 형식이 포함되어야 함
        assert "↑e" in text

    def test_load_narrative_prompt_no_persona_voice(self) -> None:
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt()
        # 꼰대 1인칭 페르소나 표현 없어야 함 (neutral tone 확인)
        assert "나는" not in text or "기록자" in text  # 기록자 언급은 허용


class TestBuildUserMessage:
    def _make_evidence(
        self,
        n_events: int = 2,
        subject_agent: str | None = None,
    ) -> object:
        from app.narrative.evidence import EventRow, Evidence

        events = [
            EventRow(
                event_id=f"aa11bb{i:02d}cc33dd44",
                ts=datetime(2026, 1, i + 1, tzinfo=UTC),
                kind="observation",
                source_agent=subject_agent or "agent_alice",
                source_type="self",
                payload={"msg": f"event_{i}"},
            )
            for i in range(n_events)
        ]
        return Evidence(events=events, reflections=[])

    def test_build_user_message_includes_question(self) -> None:
        from app.narrative.prompts import build_user_message

        evidence = self._make_evidence()
        msg = build_user_message("alice는 무엇을 했나요?", evidence)
        assert "alice는 무엇을 했나요?" in msg

    def test_build_user_message_lists_event_markers(self) -> None:
        from app.narrative.prompts import build_user_message

        evidence = self._make_evidence(n_events=2)
        msg = build_user_message("질문", evidence)
        # 이벤트 short_id 마커가 포함되어야 함
        assert "↑e" in msg

    def test_build_user_message_handles_empty_evidence(self) -> None:
        from app.narrative.evidence import Evidence
        from app.narrative.prompts import build_user_message

        empty = Evidence(events=[], reflections=[])
        msg = build_user_message("빈 DB 질문", empty)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_build_user_message_subject_label_when_present(self) -> None:
        from app.narrative.prompts import build_user_message

        evidence = self._make_evidence(subject_agent="agent_alice")
        msg = build_user_message("질문", evidence, subject_agent="agent_alice")
        assert "agent_alice" in msg

    def test_build_user_message_subject_label_none_shows_global(self) -> None:
        from app.narrative.prompts import build_user_message

        evidence = self._make_evidence()
        msg = build_user_message("질문", evidence, subject_agent=None)
        assert "전체" in msg


# ── Phase 7.5: persona selector ───────────────────────────────────────────────

class TestPersonaSelector:
    def test_load_prompt_default_returns_neutral(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No env, no arg → neutral prompt; contains '객관적'."""
        monkeypatch.delenv("OLDMAN_PERSONA", raising=False)
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt()
        assert "객관적" in text

    def test_load_prompt_with_kkondae_arg_returns_kkondae(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit arg 'kkondae' overrides env; result contains '내가'."""
        monkeypatch.setenv("OLDMAN_PERSONA", "neutral")
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt("kkondae")
        assert "내가" in text

    def test_load_prompt_reads_env_when_no_arg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OLDMAN_PERSONA=kkondae with no arg → kkondae content."""
        monkeypatch.setenv("OLDMAN_PERSONA", "kkondae")
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt()
        assert "내가" in text

    def test_load_prompt_unknown_persona_raises_value_error(self) -> None:
        """load_narrative_prompt('invalid') → ValueError."""
        import pytest as _pytest

        from app.narrative.prompts import load_narrative_prompt

        with _pytest.raises(ValueError, match="invalid"):
            load_narrative_prompt("invalid")

    def test_kkondae_prompt_file_meets_cache_floor(self) -> None:
        """prompts/narrative_kkondae.md is ≥ 1500 chars."""
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt("kkondae")
        assert len(text) >= 1500, f"kkondae prompt too short: {len(text)} chars"

    def test_kkondae_prompt_uses_first_person_voice(self) -> None:
        """kkondae prompt contains first-person markers like '내가'."""
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt("kkondae")
        assert any(marker in text for marker in ("내가", "내", "나")), (
            "kkondae prompt must contain first-person voice"
        )

    def test_neutral_prompt_does_not_use_first_person(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """neutral prompt must not use '내가' (1인칭 화자 금지)."""
        monkeypatch.delenv("OLDMAN_PERSONA", raising=False)
        from app.narrative.prompts import load_narrative_prompt

        text = load_narrative_prompt("neutral")
        # neutral prompt mentions '내가' only to *prohibit* it (in a rule statement),
        # not to speak in first-person voice. The kkondae-specific phrase is '내가 봤지'.
        assert "내가 봤지" not in text, "neutral prompt must not use '내가 봤지' (꼰대 1인칭 금지)"
