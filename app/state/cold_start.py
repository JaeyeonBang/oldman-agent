"""Cold-start signal — read-side only.

A query is "cold" when the corpus is not yet rich enough to ground a citation:
either no events have arrived, or no reflections exist yet. M1 exposes the
state; M3 ``/query`` wires it to emit the fallback message instead of an
ungrounded narrative.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

COLD_START_FALLBACK_MESSAGE = "그건 내가 못 봐서 모르겠네."


@dataclass(frozen=True)
class ColdStartState:
    event_count: int
    semantic_entity_count: int
    reflection_count: int

    @property
    def is_cold(self) -> bool:
        """True until at least one event AND one reflection exist."""
        return self.event_count == 0 or self.reflection_count == 0


def _count(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


def get_cold_start_state(conn: duckdb.DuckDBPyConnection) -> ColdStartState:
    return ColdStartState(
        event_count=_count(conn, "events"),
        semantic_entity_count=_count(conn, "entities_semantic"),
        reflection_count=_count(conn, "reflections"),
    )
