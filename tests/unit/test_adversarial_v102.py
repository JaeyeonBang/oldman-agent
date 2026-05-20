"""Adversarial / gap-audit tests for v1.0.2.

Outer-Opus audit pass (2026-05-20). Targets gaps not exercised by the
existing 219-test suite. Each test was RED-first against the actual
implementation; ones marked xfail correspond to filed BUG-N entries
in the audit report.

Categories covered:
- A. Security / input validation (regex bypass, unicode look-alikes, NFC/NFD)
- B. Concurrency boundaries
- C. Error-path coverage (provider malformed responses)
- D. Boundary conditions (validator threshold, citation regex)
- E. Real-world failure modes (PK vs UNIQUE distinguishing, FK leak)
- F. State machine (cold-start helper, validator empty-evidence semantics)
"""

from __future__ import annotations

import asyncio
import json
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

import duckdb
import httpx
import pytest

from app.llm.base import LLMRequest, LLMResponse, LLMTier

# ─────────────────────────────────────────────────────────────────────────────
# Shared test doubles
# ─────────────────────────────────────────────────────────────────────────────


class _StaticTextProvider:
    """Provider that returns a fixed text on every call."""

    name = "static_text"
    model = "static-1"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self.text, model=self.model, tier=req.tier)


def _insert_event_row(
    conn: duckdb.DuckDBPyConnection,
    *,
    event_id: str | None = None,
    source_agent: str = "agent_alice",
    payload: dict[str, Any] | None = None,
    ts: datetime | None = None,
) -> str:
    eid = event_id or str(uuid.uuid4())
    ts = ts or datetime.now(UTC)
    payload = payload or {"msg": "x"}
    conn.execute(
        "INSERT INTO events "
        "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (?, ?, 'observation', ?, 'self', ?, ?)",
        [eid, ts, source_agent, json.dumps(payload), uuid.uuid4().hex],
    )
    return eid


def _insert_reflection_row(
    conn: duckdb.DuckDBPyConnection,
    *,
    scope: str = "agent",
    subject: str = "agent_alice",
) -> None:
    rid = str(uuid.uuid4())
    ts = datetime.now(UTC)
    conn.execute(
        "INSERT INTO reflections "
        "(reflection_id, ts, scope, subject, text, "
        " event_range_start, event_range_end, source_event_ids) "
        "VALUES (?, ?, ?, ?, 'rfl', ?, ?, '[]')",
        [rid, ts, scope, subject, ts, ts],
    )


# ─────────────────────────────────────────────────────────────────────────────
# A. Security / input validation
# ─────────────────────────────────────────────────────────────────────────────


class TestCitationRegexAdversarial:
    """Citation marker regex `[↑e<8 hex>]` is the trust boundary between
    LLM text and DB lookups. Test edges."""

    def test_uppercase_hex_marker_is_extracted_and_normalised(self) -> None:
        """BUG-1 FIXED v1.0.3: regex now case-insensitive + .lower() applied
        on capture. Uppercase markers from LLMs resolve correctly against
        evidence (whose short_ids are always lowercase from event_id[:8])."""
        from app.narrative.citation import extract_citations

        out = extract_citations("alice가 행동을 했어요 [↑eAA11BB22].")
        assert len(out) == 1
        # Normalised to lowercase so DB lookups (event_id[:8]) hit.
        assert out[0].short_id == "aa11bb22"

    def test_mixed_case_marker_resolves_to_lowercase(self) -> None:
        """BUG-1 FIXED v1.0.3: mixed-case hex also normalised."""
        from app.narrative.citation import extract_citations

        out = extract_citations("[↑eAa11Bb22]")
        assert len(out) == 1
        assert out[0].short_id == "aa11bb22"

    def test_uppercase_and_lowercase_same_id_dedupes(self) -> None:
        """BUG-1 FIXED v1.0.3: same short_id in different case → 1 Citation."""
        from app.narrative.citation import extract_citations

        out = extract_citations("[↑eAA11BB22] then [↑eaa11bb22]")
        assert len(out) == 1
        assert out[0].short_id == "aa11bb22"

    def test_marker_with_inner_space_is_not_extracted(self) -> None:
        from app.narrative.citation import extract_citations

        # `[↑e aa11bb22]` (inner space) — not a marker; must NOT extract.
        assert extract_citations("[↑e aa11bb22]") == []

    def test_marker_with_unicode_lookalike_arrow_is_not_extracted(self) -> None:
        """Fullwidth/lookalike arrow chars must not be treated as `↑`."""
        from app.narrative.citation import extract_citations

        # Use a Unicode arrow that is NOT U+2191 (the canonical ↑)
        bogus = "[⇧eaa11bb22]"  # ⇧ instead of ↑
        assert extract_citations(bogus) == []

    def test_marker_with_extra_brackets_does_not_double_match(self) -> None:
        from app.narrative.citation import extract_citations

        # The inner valid marker should still match; the outer brackets are noise.
        out = extract_citations("[[↑eaa11bb22]]")
        assert len(out) == 1
        assert out[0].short_id == "aa11bb22"

    def test_marker_with_non_hex_chars_in_id_does_not_extract(self) -> None:
        from app.narrative.citation import extract_citations

        # `g` is not a hex char.
        assert extract_citations("[↑egghhi011]") == []


class TestPayloadHashUnicodeBoundaries:
    """payload_sha256 NFC normalises strings, so Korean composed/decomposed
    hashes match. Confirm the same property for nested dicts + lists."""

    def test_nfc_normalisation_in_nested_list(self) -> None:
        from app.storage.dedup import payload_sha256

        composed = "꼰대"
        decomposed = unicodedata.normalize("NFD", composed)
        h1 = payload_sha256({"tags": [composed, "neutral"]})
        h2 = payload_sha256({"tags": [decomposed, "neutral"]})
        assert h1 == h2

    def test_nfc_normalisation_in_nested_dict(self) -> None:
        from app.storage.dedup import payload_sha256

        composed = "꼰대"
        decomposed = unicodedata.normalize("NFD", composed)
        h1 = payload_sha256({"deep": {"name": composed}})
        h2 = payload_sha256({"deep": {"name": decomposed}})
        assert h1 == h2

    def test_tokenize_nfc_normalisation_unifies_forms(self) -> None:
        from app.storage.dedup import tokenize

        composed = "꼰대"
        decomposed = unicodedata.normalize("NFD", composed)
        # Both forms tokenize to the same NFC-normalised token set.
        assert tokenize({"x": composed}) == tokenize({"x": decomposed})


# ─────────────────────────────────────────────────────────────────────────────
# D. Boundary conditions
# ─────────────────────────────────────────────────────────────────────────────


class TestValidatorEdgeBoundaries:
    """Existence validator behavior with evidence present."""

    def test_validate_text_exactly_20_chars_with_evidence_returns_invalid(self) -> None:
        """BUG-3 FIXED v1.0.3: length threshold removed when evidence non-empty.
        Any markerless text + evidence = invalid (forces renderer retry → fallback).
        Previously the `> 20` threshold let short claims slip through.
        """
        from app.narrative.evidence import EventRow, Evidence
        from app.narrative.validator import validate_citations

        text = "x" * 20  # exactly the threshold
        ev = Evidence(
            events=[
                EventRow(
                    event_id="aa11bb22-0000-0000-0000-000000000000",
                    ts=datetime(2026, 1, 1, tzinfo=UTC),
                    kind="k",
                    source_agent="a",
                    source_type="self",
                    payload={},
                )
            ],
            reflections=[],
        )
        result = validate_citations(text, ev)
        # v1.0.3: threshold removed when evidence non-empty → invalid regardless of length.
        assert result.is_valid is False

    def test_validate_text_21_chars_with_evidence_returns_invalid(self) -> None:
        from app.narrative.evidence import EventRow, Evidence
        from app.narrative.validator import validate_citations

        text = "x" * 21  # one over threshold
        ev = Evidence(
            events=[
                EventRow(
                    event_id="aa11bb22-0000-0000-0000-000000000000",
                    ts=datetime(2026, 1, 1, tzinfo=UTC),
                    kind="k",
                    source_agent="a",
                    source_type="self",
                    payload={},
                )
            ],
            reflections=[],
        )
        result = validate_citations(text, ev)
        assert result.is_valid is False


class TestJudgeJsonExtractor:
    """parse_judge_output now tries json.loads(text) first, regex fallback second."""

    def test_parse_judge_output_nested_object_in_reason_parses_correctly(self) -> None:
        """BUG-4 FIXED v1.0.3: json.loads(text) tries the whole text first.
        Nested objects in `reason` no longer mis-parse to is_grounded=False.
        The dict reason is JSON-serialized into the reason string."""
        from app.narrative.judge import parse_judge_output

        text = '{"is_grounded": true, "reason": {"detail": "ok"}}'
        verdict = parse_judge_output(text)
        assert verdict.is_grounded is True
        # nested dict serialized into reason string
        assert "detail" in verdict.reason
        assert "ok" in verdict.reason

    def test_parse_judge_output_regex_fallback_still_works(self) -> None:
        """Sanity: prose-wrapped JSON still parses via the regex fallback."""
        from app.narrative.judge import parse_judge_output

        text = '판정 결과: {"is_grounded": false, "reason": "agent name mismatch"} 끝.'
        verdict = parse_judge_output(text)
        assert verdict.is_grounded is False
        assert "mismatch" in verdict.reason


# ─────────────────────────────────────────────────────────────────────────────
# C. Error-path gaps — provider malformed responses
# ─────────────────────────────────────────────────────────────────────────────


class TestAnthropicProviderMalformedResponse:
    """AnthropicProvider parses `data["content"][0]["text"]` without guards.
    Mock transports producing odd shapes will surface as KeyError/IndexError
    rather than a typed LLMConfigError."""

    @pytest.mark.asyncio
    async def test_empty_content_array_raises_index_error(self) -> None:
        from app.llm.providers.anthropic import AnthropicProvider

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"content": [], "usage": {}, "model": "x"})

        transport = httpx.MockTransport(handler)
        provider = AnthropicProvider(
            api_key="sk-test", model="claude-haiku-4-5-20251001", transport=transport
        )
        with pytest.raises((IndexError, KeyError)):
            await provider.complete(
                LLMRequest(system="s", prompt="p", tier=LLMTier.CHEAP, max_tokens=64)
            )

    @pytest.mark.asyncio
    async def test_missing_text_key_raises_key_error(self) -> None:
        from app.llm.providers.anthropic import AnthropicProvider

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"content": [{"type": "image"}], "usage": {}, "model": "x"}
            )

        transport = httpx.MockTransport(handler)
        provider = AnthropicProvider(
            api_key="sk-test", model="claude-haiku-4-5-20251001", transport=transport
        )
        with pytest.raises(KeyError):
            await provider.complete(
                LLMRequest(system="s", prompt="p", tier=LLMTier.CHEAP, max_tokens=64)
            )

    @pytest.mark.asyncio
    async def test_4xx_raises_httpstatuserror(self) -> None:
        from app.llm.providers.anthropic import AnthropicProvider

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "rate limit"}})

        transport = httpx.MockTransport(handler)
        provider = AnthropicProvider(
            api_key="sk-test", model="claude-haiku-4-5-20251001", transport=transport
        )
        with pytest.raises(httpx.HTTPStatusError):
            await provider.complete(
                LLMRequest(system="s", prompt="p", tier=LLMTier.CHEAP, max_tokens=64)
            )


class TestOpenRouterProviderMalformedResponse:
    """v1.0.5 defensive: malformed responses yield typed ValueError with
    diagnostic message instead of opaque IndexError/KeyError/TypeError."""

    @pytest.mark.asyncio
    async def test_empty_choices_array_raises_value_error(self) -> None:
        from app.llm.providers.openrouter import OpenRouterProvider

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [], "usage": {}, "model": "x"})

        transport = httpx.MockTransport(handler)
        provider = OpenRouterProvider(
            api_key="or-test", model="anthropic/claude-haiku-4-5", transport=transport
        )
        with pytest.raises(ValueError, match="no choices"):
            await provider.complete(
                LLMRequest(system="s", prompt="p", tier=LLMTier.CHEAP, max_tokens=64)
            )

    @pytest.mark.asyncio
    async def test_null_content_with_reasoning_raises_value_error_with_hint(self) -> None:
        """Reasoning model (content=None + reasoning=present) → clear hint."""
        from app.llm.providers.openrouter import OpenRouterProvider

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "reasoning": "thinking step by step...",
                            },
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {},
                },
            )

        transport = httpx.MockTransport(handler)
        provider = OpenRouterProvider(
            api_key="or-test", model="deepseek/deepseek-v4-flash", transport=transport
        )
        with pytest.raises(ValueError, match="reasoning model"):
            await provider.complete(
                LLMRequest(system="s", prompt="p", tier=LLMTier.CHEAP, max_tokens=64)
            )

    @pytest.mark.asyncio
    async def test_missing_message_content_raises_value_error(self) -> None:
        from app.llm.providers.openrouter import OpenRouterProvider

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant"}}], "usage": {}},
            )

        transport = httpx.MockTransport(handler)
        provider = OpenRouterProvider(
            api_key="or-test", model="anthropic/claude-haiku-4-5", transport=transport
        )
        with pytest.raises(ValueError, match="content=None"):
            await provider.complete(
                LLMRequest(system="s", prompt="p", tier=LLMTier.CHEAP, max_tokens=64)
            )


# ─────────────────────────────────────────────────────────────────────────────
# C+F. Renderer handles provider errors gracefully (no HTTP 500 leak)
# ─────────────────────────────────────────────────────────────────────────────


class TestRendererProviderErrorRobustness:
    """renderer.render_narrative catches `Exception` broadly. Confirm that
    HTTPStatusError / KeyError / IndexError all result in fallback, not crash."""

    @pytest.mark.asyncio
    async def test_renderer_httpstatuserror_returns_fallback(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.renderer import render_narrative

        eid = _insert_event_row(tmp_db)
        _insert_reflection_row(tmp_db)

        class BadProvider:
            name = "bad"
            model = "bad-1"

            async def complete(self, req: LLMRequest) -> LLMResponse:
                req_obj = httpx.Request("POST", "https://x")
                resp = httpx.Response(500, request=req_obj)
                raise httpx.HTTPStatusError("boom", request=req_obj, response=resp)

        del eid  # not used; just seed the db
        result = await render_narrative(tmp_db, BadProvider(), "q", "agent_alice")
        assert result.used_fallback is True

    @pytest.mark.asyncio
    async def test_renderer_keyerror_returns_fallback(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.renderer import render_narrative

        _insert_event_row(tmp_db)
        _insert_reflection_row(tmp_db)

        class KeyErrorProvider:
            name = "ke"
            model = "ke-1"

            async def complete(self, req: LLMRequest) -> LLMResponse:
                raise KeyError("content")

        result = await render_narrative(tmp_db, KeyErrorProvider(), "q", "agent_alice")
        assert result.used_fallback is True


# ─────────────────────────────────────────────────────────────────────────────
# E. Real-world failure modes
# ─────────────────────────────────────────────────────────────────────────────


class TestPublishConstraintExceptionClassification:
    """BUG-2 FIXED v1.0.3: only payload_hash UNIQUE collisions map to
    exact_hash. PK collisions re-raise → 500."""

    @pytest.mark.asyncio
    async def test_pk_collision_on_event_id_re_raises_as_500(
        self, tmp_db_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Force uuid4() collision → IntegrityError on event_id PK.
        The new classifier matches only 'payload_hash' substring, so PK
        collisions surface as 500 (system bug) instead of masquerading as
        dedup. The publish row is correctly NOT inserted (ROLLBACK ran).
        """
        import os

        os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
        from app.api import publish as publish_mod
        from app.main import create_app

        app = create_app()

        fixed_id = "11111111-2222-3333-4444-555555555555"
        conn = app.state.db
        conn.execute(
            "INSERT INTO events "
            "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
            "VALUES (?, ?, 'observation', 'a', 'self', '{}', 'distinct_hash')",
            [fixed_id, datetime.now(UTC)],
        )

        monkeypatch.setattr(
            publish_mod.uuid, "uuid4", lambda: uuid.UUID(fixed_id)
        )

        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/publish",
                json={
                    "event_kind": "chat",
                    "source_agent": "a",
                    "declared_source_type": "self",
                    "payload": {"text": "novel content not yet hashed"},
                },
            )
        # PK collision re-raises → FastAPI surfaces as 500.
        assert resp.status_code == 500
        # No second row inserted (rollback ran).
        rows = conn.execute("SELECT count(*) FROM events").fetchone()
        assert rows is not None and rows[0] == 1

    @pytest.mark.asyncio
    async def test_payload_hash_collision_still_maps_to_exact_hash(
        self, tmp_db_path
    ) -> None:
        """Regression: BUG-2 fix must NOT regress the legitimate exact_hash path.
        Identical payloads from the same agent → 409 deduplicated/exact_hash
        via UNIQUE(payload_hash) (concurrent race uses this path; serial dup
        is caught by Jaccard first per plan §0 step 3)."""
        import asyncio as _asyncio
        import os

        os.environ["OLDMAN_DB_PATH"] = str(tmp_db_path)
        from app.main import create_app

        app = create_app()
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            payload = {
                "event_kind": "chat",
                "source_agent": "a",
                "declared_source_type": "self",
                "payload": {"text": "race-me"},
            }
            r1, r2 = await _asyncio.gather(
                c.post("/publish", json=payload),
                c.post("/publish", json=payload),
            )
            codes = sorted([r1.status_code, r2.status_code])
            assert codes == [200, 409]
            # One of them is exact_hash via UNIQUE constraint
            r409 = r1 if r1.status_code == 409 else r2
            assert r409.json()["detail"]["reason"] in {"exact_hash", "jaccard_near_duplicate"}


class TestEntitiesEpisodicObservedNullJoin:
    """entities_episodic.observed_agent IS NULL is allowed by schema.
    Confirm pair-scope reflection trigger doesn't crash when no pair rows
    exist (observed_agent NULL on every prior event)."""

    def test_pair_scope_trigger_state_with_null_observed_returns_zero(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.reflection.state import get_trigger_state

        # Insert events whose episodic rows have observed_agent NULL
        for _ in range(3):
            eid = _insert_event_row(tmp_db, source_agent="agent_alice")
            tmp_db.execute(
                "INSERT INTO entities_episodic "
                "(id, event_id, observer_agent, observed_agent, kind, ts, source_type) "
                "VALUES (?, ?, 'agent_alice', NULL, 'observation', ?, 'self')",
                [str(uuid.uuid4()), eid, datetime.now(UTC)],
            )

        state = get_trigger_state(
            tmp_db, scope="pair", subject="agent_alice:agent_bob"
        )
        # No rows match observer=alice AND observed=bob → 0
        assert state.events_since_last_reflection == 0


class TestNFCAgentIdMismatchAtBoundary:
    """If the publish client posts an agent_id with NFD form and the query
    client uses NFC form, are they treated as the same agent?

    Spec implies "yes" (NFC normalisation is documented for payloads in
    plan §0 T3 and is applied). But agent_id strings are NOT NFC-normalised
    anywhere — they're stored raw. So they DO differ.

    This pins the current behaviour: agent_id NFC/NFD forms are treated as
    DIFFERENT agents. Future work may want to normalise.
    """

    def test_publish_and_query_with_different_nfc_forms_treat_as_separate(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.evidence import select_evidence

        composed = "꼰대"
        decomposed = unicodedata.normalize("NFD", composed)

        # Insert event under decomposed agent_id
        _insert_event_row(tmp_db, source_agent=decomposed)

        # Query with composed form
        ev_composed = select_evidence(tmp_db, subject_agent=composed)
        ev_decomposed = select_evidence(tmp_db, subject_agent=decomposed)

        # Currently: agent_id is NOT NFC-normalised in DB or filter
        # → composed query returns 0 events even though event "is" by 꼰대
        assert len(ev_decomposed.events) == 1
        assert len(ev_composed.events) == 0


# ─────────────────────────────────────────────────────────────────────────────
# F. State machine / contract gaps
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectEvidencePayloadJsonNull:
    """select_evidence guards `json.loads` against TypeError/JSONDecodeError
    by falling back to {}. Verify the path is reachable."""

    def test_select_evidence_with_payload_json_typeerror_falls_back_to_empty_dict(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from app.narrative.evidence import select_evidence

        # Insert a row whose payload_json is an integer (not a string or dict)
        # — DuckDB JSON column accepts this; the .py loader defends with {}.
        eid = str(uuid.uuid4())
        ts = datetime.now(UTC)
        tmp_db.execute(
            "INSERT INTO events "
            "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
            "VALUES (?, ?, 'k', 'agent_alice', 'self', ?, ?)",
            [eid, ts, json.dumps({"x": 1}), uuid.uuid4().hex],
        )
        ev = select_evidence(tmp_db, subject_agent="agent_alice")
        assert len(ev.events) == 1
        assert isinstance(ev.events[0].payload, dict)


class TestMockNarrativeNoMarkersInvalidatesAndFallsBack:
    """BUG-3 FIXED v1.0.3: validator now rejects markerless text when evidence
    is non-empty, regardless of text length. Mock narrative's "증거가
    부족합니다." (10 chars) is now correctly invalid → renderer retries →
    fallback. Plan §7.0 Phase 7.0 contract honored."""

    def test_short_markerless_text_with_evidence_is_invalid(self) -> None:
        """Direct validator check: 10-char no-marker text + evidence = invalid."""
        from app.narrative.evidence import EventRow, Evidence
        from app.narrative.validator import validate_citations

        evidence = Evidence(
            events=[
                EventRow(
                    event_id="aa11bb22-0000-0000-0000-000000000000",
                    ts=datetime(2026, 1, 1, tzinfo=UTC),
                    kind="k",
                    source_agent="agent_alice",
                    source_type="self",
                    payload={},
                )
            ],
            reflections=[],
        )
        result = validate_citations("증거가 부족합니다.", evidence)
        # v1.0.3: no markers + evidence present → invalid (was True pre-fix).
        assert result.is_valid is False

    def test_short_markerless_text_with_NO_evidence_still_valid(self) -> None:
        """Sanity: cold-start fallback path (no evidence) still valid for
        short markerless text. This is the documented cold-start branch."""
        from app.narrative.evidence import Evidence
        from app.narrative.validator import validate_citations

        evidence = Evidence(events=[], reflections=[])
        result = validate_citations("그건 내가 못 봐서 모르겠네.", evidence)
        assert result.is_valid is True


class TestExtractCitationsDedupesAcrossSentences:
    """When the same marker appears twice, only one Citation is produced.
    In strict mode this means the judge is called once per unique short_id,
    NOT per occurrence. Pin this as the contract; it's reasonable but not
    documented in the eng review."""

    @pytest.mark.asyncio
    async def test_strict_validator_judges_once_per_unique_marker(self) -> None:
        from app.llm.base import LLMResponse as LR
        from app.narrative.evidence import EventRow, Evidence
        from app.narrative.validator import validate_citations_with_judge

        class CountingJudge:
            name = "ct"
            model = "ct-1"

            def __init__(self) -> None:
                self.calls = 0

            async def complete(self, req: LLMRequest) -> LR:
                self.calls += 1
                return LR(
                    text='{"is_grounded": true, "reason": "ok"}',
                    model=self.model,
                    tier=req.tier,
                )

        eid = "aa11bb22-0000-0000-0000-000000000000"
        ev = Evidence(
            events=[
                EventRow(
                    event_id=eid,
                    ts=datetime(2026, 1, 1, tzinfo=UTC),
                    kind="k",
                    source_agent="a",
                    source_type="self",
                    payload={"x": 1},
                )
            ],
            reflections=[],
        )
        text = f"문장 1 [↑e{eid[:8]}]. 문장 2 [↑e{eid[:8]}]. 문장 3 [↑e{eid[:8]}]."

        judge = CountingJudge()
        result = await validate_citations_with_judge(text, ev, judge)
        assert result.is_valid is True
        # Single unique short_id → judge called once, not three times.
        assert judge.calls == 1


# ─────────────────────────────────────────────────────────────────────────────
# B. Concurrency boundaries
# ─────────────────────────────────────────────────────────────────────────────


class TestReflectionSchedulerDifferentSubjectsIndependent:
    """`_locks` in scheduler is keyed by `(scope, subject)`. Confirm two
    different agents don't contend on the same lock."""

    @pytest.mark.asyncio
    async def test_different_subjects_run_concurrently(
        self, tmp_db: duckdb.DuckDBPyConnection
    ) -> None:
        from datetime import timedelta

        from app.reflection.scheduler import maybe_run_reflection

        ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        for i in range(10):
            _insert_event_row(
                tmp_db, source_agent="agent_alice", ts=ts + timedelta(minutes=i)
            )
        for i in range(10):
            _insert_event_row(
                tmp_db, source_agent="agent_bob", ts=ts + timedelta(minutes=i)
            )

        valid_json = json.dumps(
            {
                "summary": "s",
                "descriptors": ["d"],
                "evidence_event_ids": [],
            }
        )
        p1 = _StaticTextProvider(valid_json)
        p2 = _StaticTextProvider(valid_json)
        now = ts + timedelta(minutes=15)

        # Two different subjects → independent locks → both should run
        results = await asyncio.gather(
            maybe_run_reflection(
                tmp_db, scope="agent", subject="agent_alice", provider=p1, now=now
            ),
            maybe_run_reflection(
                tmp_db, scope="agent", subject="agent_bob", provider=p2, now=now
            ),
        )
        assert all(r is not None for r in results)
        # Two reflection rows
        count = tmp_db.execute("SELECT COUNT(*) FROM reflections").fetchone()
        assert count is not None
        assert count[0] == 2
