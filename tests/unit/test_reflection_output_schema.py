"""Phase 2.4 — RED tests for TraitsCompiled pydantic model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.reflection.output_schema import TraitsCompiled


class TestTraitsCompiled:
    def test_valid_model_parses(self) -> None:
        data = {
            "summary": "테스트 요약",
            "descriptors": ["감시형", "고빈도"],
            "evidence_event_ids": ["e001", "e002"],
        }
        m = TraitsCompiled.model_validate(data)
        assert m.summary == "테스트 요약"
        assert m.descriptors == ["감시형", "고빈도"]
        assert m.evidence_event_ids == ["e001", "e002"]

    def test_missing_summary_raises(self) -> None:
        with pytest.raises(ValidationError):
            TraitsCompiled.model_validate(
                {"descriptors": ["x"], "evidence_event_ids": []}
            )

    def test_descriptors_must_be_list(self) -> None:
        with pytest.raises(ValidationError):
            TraitsCompiled.model_validate(
                {"summary": "s", "descriptors": "not a list", "evidence_event_ids": []}
            )

    def test_evidence_event_ids_empty_allowed(self) -> None:
        m = TraitsCompiled.model_validate(
            {"summary": "s", "descriptors": ["x"], "evidence_event_ids": []}
        )
        assert m.evidence_event_ids == []

    def test_extra_keys_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            TraitsCompiled.model_validate(
                {
                    "summary": "s",
                    "descriptors": ["x"],
                    "evidence_event_ids": [],
                    "extra_field": "잘못된_키",
                }
            )

    def test_from_json_text_parses(self) -> None:
        raw = '{"summary":"테스트","descriptors":["a"],"evidence_event_ids":["e1"]}'
        m = TraitsCompiled.model_validate_json(raw)
        assert m.summary == "테스트"
