"""Runtime settings (env-overridable).

DuckDB is single-writer — uvicorn MUST run with ``--workers 1``. ``db_path``
defaults to ``./oldman.duckdb`` (gitignored) and is overridable via
``OLDMAN_DB_PATH``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str
    jaccard_window: int
    jaccard_threshold: float

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            db_path=os.environ.get("OLDMAN_DB_PATH", "./oldman.duckdb"),
            jaccard_window=int(os.environ.get("OLDMAN_JACCARD_WINDOW", "50")),
            jaccard_threshold=float(os.environ.get("OLDMAN_JACCARD_THRESHOLD", "0.9")),
        )


def get_settings() -> Settings:
    return Settings.from_env()
