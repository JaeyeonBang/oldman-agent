"""Phase 3.3 — RED tests: citation validator."""

from __future__ import annotations

from datetime import UTC, datetime


def _make_evidence(event_ids: list[str]) -> object:
    from app.narrative.evidence import EventRow, Evidence

    events = [
        EventRow(
            event_id=eid,
            ts=datetime(2026, 1, 1, tzinfo=UTC),
            kind="observation",
            source_agent="agent_alice",
            source_type="self",
            payload={"msg": "test"},
        )
        for eid in event_ids
    ]
    return Evidence(events=events, reflections=[])


class TestValidateCitations:
    def test_validate_all_markers_present_returns_valid(self) -> None:
        from app.narrative.validator import validate_citations

        event_id = "aa11bb22-0000-0000-0000-000000000000"
        evidence = _make_evidence([event_id])
        text = "agent_alice가 행동을 했습니다 [↑eaa11bb22]."
        result = validate_citations(text, evidence)
        assert result.is_valid is True
        assert result.missing == []

    def test_validate_missing_marker_returns_invalid(self) -> None:
        from app.narrative.validator import validate_citations

        event_id = "aa11bb22-0000-0000-0000-000000000000"
        evidence = _make_evidence([event_id])
        # 마커가 DB에 없는 short_id 사용
        text = "agent_alice가 행동을 했습니다 [↑eff00ff00]."
        result = validate_citations(text, evidence)
        assert result.is_valid is False
        assert "ff00ff00" in result.missing

    def test_validate_no_markers_in_non_trivial_text_returns_invalid(self) -> None:
        from app.narrative.validator import validate_citations

        event_id = "aa11bb22-0000-0000-0000-000000000000"
        evidence = _make_evidence([event_id])
        # 20자 초과 텍스트인데 마커가 없음
        text = "agent_alice가 매우 활발하게 활동했습니다. 여러 에이전트와 상호작용했습니다."
        result = validate_citations(text, evidence)
        assert result.is_valid is False

    def test_validate_fallback_message_passes_without_citations(self) -> None:
        from app.narrative.evidence import Evidence
        from app.narrative.validator import validate_citations

        # 이벤트 없는 evidence (빈 DB) — fallback 경로
        empty_evidence = Evidence(events=[], reflections=[])
        text = "증거가 부족합니다. 이벤트가 수집된 후 다시 질의하세요."
        result = validate_citations(text, empty_evidence)
        # evidence가 비어 있으면 마커 없어도 valid
        assert result.is_valid is True

    def test_validate_short_id_prefix_match(self) -> None:
        from app.narrative.validator import validate_citations

        # full UUID: aa11bb22-ccdd-eeff-0011-223344556677
        event_id = "aa11bb22-ccdd-eeff-0011-223344556677"
        evidence = _make_evidence([event_id])
        # 앞 8자리 aa11bb22 으로 마커 작성
        text = "이벤트가 발생했습니다 [↑eaa11bb22]."
        result = validate_citations(text, evidence)
        assert result.is_valid is True

    def test_validate_extracted_citations_populated(self) -> None:
        from app.narrative.validator import validate_citations

        event_id = "aa11bb22-0000-0000-0000-000000000000"
        evidence = _make_evidence([event_id])
        text = "행동이 확인됩니다 [↑eaa11bb22]."
        result = validate_citations(text, evidence)
        assert len(result.extracted) == 1
        assert result.extracted[0].short_id == "aa11bb22"

    def test_validate_empty_text_with_evidence_invalid(self) -> None:
        """v1.0.3 BUG-3 fix: evidence가 있으면 마커 없는 텍스트는 길이 무관 invalid.
        빈 텍스트는 provider 빈 응답 신호 → retry → fallback이 옳음."""
        from app.narrative.validator import validate_citations

        event_id = "aa11bb22-0000-0000-0000-000000000000"
        evidence = _make_evidence([event_id])
        result = validate_citations("", evidence)
        assert result.is_valid is False
