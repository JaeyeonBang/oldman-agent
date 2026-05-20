"""Phase 1.6 RED: cold-start helper paths."""

from __future__ import annotations

import duckdb

from app.state.cold_start import COLD_START_FALLBACK_MESSAGE, get_cold_start_state


def test_fallback_message_constant() -> None:
    assert COLD_START_FALLBACK_MESSAGE == "그건 내가 못 봐서 모르겠네."


def test_cold_on_empty_db(tmp_db: duckdb.DuckDBPyConnection) -> None:
    state = get_cold_start_state(tmp_db)
    assert state.event_count == 0
    assert state.semantic_entity_count == 0
    assert state.reflection_count == 0
    assert state.is_cold is True


def test_still_cold_when_only_events_present(tmp_db: duckdb.DuckDBPyConnection) -> None:
    tmp_db.execute(
        "INSERT INTO events "
        "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (uuid(), now(), 'chat', 'a', 'self', '{}', 'h1')"
    )
    state = get_cold_start_state(tmp_db)
    assert state.event_count == 1
    assert state.reflection_count == 0
    assert state.is_cold is True


def test_not_cold_when_both_events_and_reflections(tmp_db: duckdb.DuckDBPyConnection) -> None:
    tmp_db.execute(
        "INSERT INTO events "
        "(event_id, ts, kind, source_agent, source_type, payload_json, payload_hash) "
        "VALUES (uuid(), now(), 'chat', 'a', 'self', '{}', 'h2')"
    )
    tmp_db.execute(
        "INSERT INTO reflections "
        "(reflection_id, ts, scope, subject, text, event_range_start, "
        " event_range_end, source_event_ids) "
        "VALUES (uuid(), now(), 'agent', 'a', 't', now(), now(), '[]')"
    )
    state = get_cold_start_state(tmp_db)
    assert state.is_cold is False


def test_semantic_count_tracks_publishes(tmp_db: duckdb.DuckDBPyConnection) -> None:
    tmp_db.execute(
        "INSERT INTO entities_semantic "
        "(agent_id, source_type, first_seen_ts, last_updated) "
        "VALUES ('alice', 'self', now(), now())"
    )
    state = get_cold_start_state(tmp_db)
    assert state.semantic_entity_count == 1
