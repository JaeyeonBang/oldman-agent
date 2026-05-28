"""Unit tests for app.narrative.smalltalk — v2.4 화이트리스트."""

from __future__ import annotations

import pytest

from app.narrative.smalltalk import match_smalltalk


class TestGreeting:
    @pytest.mark.parametrize(
        "q",
        ["안녕", "안녕하세요", "안녕!", "hi", "Hi", "Hello!", "hey there", "반갑습니다"],
    )
    def test_greeting_matches(self, q: str) -> None:
        assert match_smalltalk(q) is not None, q

    def test_greeting_persona_differs(self) -> None:
        a = match_smalltalk("안녕", persona="kkondae")
        b = match_smalltalk("안녕", persona="neutral")
        assert a is not None and b is not None
        assert a != b
        assert "자네" in a  # kkondae 톤
        assert "oldman_agent" in b  # neutral 자기소개


class TestIdentity:
    @pytest.mark.parametrize(
        "q",
        [
            "너는 누구야?",
            "누구세요?",
            "자기소개 해줘",
            "뭐 하는 agent야?",
            "What are you?",
            "who are you",
        ],
    )
    def test_identity_matches(self, q: str) -> None:
        r = match_smalltalk(q, persona="neutral")
        assert r is not None
        assert "oldman_agent" in r or "메타-기록자" in r


class TestCapability:
    @pytest.mark.parametrize(
        "q",
        ["뭐 할 수 있어?", "기능이 뭐야", "어떻게 써?", "what can you do"],
    )
    def test_capability_matches(self, q: str) -> None:
        r = match_smalltalk(q)
        assert r is not None


class TestFarewellThanksSmallTalk:
    def test_farewell(self) -> None:
        assert match_smalltalk("잘 가") is not None
        assert match_smalltalk("bye") is not None

    def test_thanks(self) -> None:
        assert match_smalltalk("고마워") is not None
        assert match_smalltalk("thanks") is not None

    def test_smalltalk_state(self) -> None:
        assert match_smalltalk("잘 지내?") is not None
        assert match_smalltalk("how are you") is not None


class TestNoMatch:
    @pytest.mark.parametrize(
        "q",
        [
            "agent_alice 요즘 어땠나?",
            "alice가 bob한테 뭘 했지",
            "scout가 본 게 뭐야",
            "최근 동네 분위기는?",
            "carol의 평판",
        ],
    )
    def test_real_query_not_matched(self, q: str) -> None:
        assert match_smalltalk(q) is None, q

    def test_too_long_falls_through(self) -> None:
        # 인삿말 포함되어 있어도 길면 정보 요청으로 본다.
        long_q = "안녕, agent_alice가 지난 주에 어떤 활동을 했는지 자세히 알려줘"
        assert match_smalltalk(long_q) is None

    def test_empty(self) -> None:
        assert match_smalltalk("") is None
        assert match_smalltalk("   ") is None
        assert match_smalltalk("\n\t") is None


class TestPersonaResolution:
    def test_env_default_used_when_persona_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLDMAN_PERSONA", "kkondae")
        r = match_smalltalk("안녕")
        assert r is not None
        assert "자네" in r

    def test_unknown_persona_falls_back_to_neutral(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLDMAN_PERSONA", raising=False)
        r = match_smalltalk("안녕", persona="weird")
        assert r is not None
        assert "안녕하세요" in r  # neutral 응답
