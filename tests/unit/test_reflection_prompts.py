"""Phase 2.2 — RED tests: reflection prompt loader + user message builder."""

from __future__ import annotations

import pytest

from app.reflection.prompts import build_user_message, load_prompt


class TestLoadPrompt:
    def test_load_prompt_returns_system_and_user_templates_agent(self) -> None:
        system, user_tmpl = load_prompt("agent")
        assert isinstance(system, str)
        assert isinstance(user_tmpl, str)
        assert len(system) > 0
        assert len(user_tmpl) > 0

    def test_load_prompt_returns_system_and_user_templates_pair(self) -> None:
        system, _user_tmpl = load_prompt("pair")
        assert isinstance(system, str)
        assert len(system) > 0

    def test_load_prompt_returns_system_and_user_templates_society(self) -> None:
        system, _user_tmpl = load_prompt("society")
        assert isinstance(system, str)
        assert len(system) > 0

    def test_load_prompt_unknown_scope_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown scope"):
            load_prompt("unknown_scope")

    def test_load_prompt_system_exceeds_cache_floor(self) -> None:
        """시스템 프롬프트가 프롬프트 캐싱 최소 토큰(≥1024)을 넘어야 함.

        정확한 토크나이저 없이 단어 수로 추정: 영어 평균 1.3 tok/word.
        1024 / 1.3 ≈ 788 단어 → 보수적으로 700 단어 이상 요구.
        """
        for scope in ("agent", "pair", "society"):
            system, _ = load_prompt(scope)
            word_count = len(system.split())
            assert word_count >= 700, (
                f"scope={scope} system prompt too short ({word_count} words); "
                "must exceed ~1024 tokens for prompt caching"
            )


class TestBuildUserMessage:
    def test_build_user_message_includes_event_ids_and_kinds(self) -> None:
        events = [
            {"event_id": "e001", "kind": "observation", "payload": {"msg": "hello"}},
            {"event_id": "e002", "kind": "action", "payload": {"msg": "world"}},
        ]
        msg = build_user_message(events)
        assert "e001" in msg
        assert "e002" in msg
        assert "observation" in msg
        assert "action" in msg

    def test_build_user_message_truncates_to_N_recent(self) -> None:
        events = [
            {"event_id": f"e{i:03d}", "kind": "observation", "payload": {"i": i}}
            for i in range(20)
        ]
        msg = build_user_message(events, n=5)
        # 마지막 5개(e015~e019)만 포함돼야 함
        assert "e019" in msg
        assert "e015" in msg
        assert "e000" not in msg
        assert "e014" not in msg

    def test_build_user_message_empty_events(self) -> None:
        msg = build_user_message([])
        assert isinstance(msg, str)
        assert len(msg) > 0  # 빈 이벤트 안내 문구 있어야 함
