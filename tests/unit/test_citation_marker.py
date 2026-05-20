"""Phase 3.0 — RED tests: citation marker + QueryRequest/QueryResponse schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestFormatMarker:
    def test_format_marker_truncates_to_8_chars(self) -> None:
        from app.narrative.citation import format_marker

        full_id = "aa11bb22cc33dd44"
        marker = format_marker(full_id)
        assert marker == "[↑eaa11bb22]"

    def test_format_marker_exact_8_chars(self) -> None:
        from app.narrative.citation import format_marker

        short_id = "12345678"
        assert format_marker(short_id) == "[↑e12345678]"

    def test_format_marker_shorter_than_8_uses_full(self) -> None:
        from app.narrative.citation import format_marker

        short_id = "abcd"
        assert format_marker(short_id) == "[↑eabcd]"


class TestExtractCitations:
    def test_extract_citations_finds_all_markers(self) -> None:
        from app.narrative.citation import extract_citations

        text = "alice가 [↑eaa11bb22] 행동을 했고 bob도 [↑ecc33dd44] 반응했다."
        results = extract_citations(text)
        assert len(results) == 2
        sids = [c.short_id for c in results]
        assert "aa11bb22" in sids
        assert "cc33dd44" in sids

    def test_extract_citations_empty_text_returns_empty_list(self) -> None:
        from app.narrative.citation import extract_citations

        assert extract_citations("") == []

    def test_extract_citations_dedupes_same_marker(self) -> None:
        from app.narrative.citation import extract_citations

        text = "[↑eaa11bb22] 중복 [↑eaa11bb22] 발생"
        results = extract_citations(text)
        assert len(results) == 1
        assert results[0].short_id == "aa11bb22"

    def test_extract_citations_no_markers_returns_empty(self) -> None:
        from app.narrative.citation import extract_citations

        assert extract_citations("아무 인용도 없는 텍스트") == []


class TestQuerySchemas:
    def test_query_request_rejects_empty_question(self) -> None:
        from app.api.schemas import QueryRequest

        with pytest.raises(ValidationError):
            QueryRequest(question="", subject_agent=None, max_citations=10)

    def test_query_request_rejects_long_question(self) -> None:
        from app.api.schemas import QueryRequest

        with pytest.raises(ValidationError):
            QueryRequest(question="x" * 1001, subject_agent=None, max_citations=10)

    def test_query_request_max_citations_bounds(self) -> None:
        from app.api.schemas import QueryRequest

        with pytest.raises(ValidationError):
            QueryRequest(question="유효한 질문", subject_agent=None, max_citations=0)
        with pytest.raises(ValidationError):
            QueryRequest(question="유효한 질문", subject_agent=None, max_citations=101)

    def test_query_request_valid(self) -> None:
        from app.api.schemas import QueryRequest

        req = QueryRequest(question="alice는 누구인가?", subject_agent="agent_alice", max_citations=10)
        assert req.question == "alice는 누구인가?"
        assert req.subject_agent == "agent_alice"
        assert req.max_citations == 10

    def test_citation_schema(self) -> None:
        from app.api.schemas import Citation

        c = Citation(short_id="aa11bb22", event_id="aa11bb22-1234-5678-abcd-000000000000")
        assert c.short_id == "aa11bb22"
