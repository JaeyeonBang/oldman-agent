"""Dedup primitives — exact hash + Jaccard near-duplicate.

::

    Dedup pipeline (two independent layers; either trips → no insert):

      Layer 1 — exact hash (race-safe backstop):
        payload (dict) ──▶ _canon (NFC normalize, sorted keys)
                       ──▶ json.dumps compact
                       ──▶ sha256 hex  ═══▶  events.payload_hash
                                                    │
                                                    ▼
                              UNIQUE constraint (migrations/001_init.sql:16)
                                                    │
                                            duplicate INSERT
                                                    ▼
                                            IntegrityError
                                                    │
                                  (publish.py classifier: msg ⊃ 'payload_hash')
                                                    ▼
                                          ExactHashDuplicateError
                                  (T1 + T4 race-safety backstop; survives
                                   future async/multi-conn DB evolution)

      Layer 2 — Jaccard near-dup (sliding window):
        payload (dict) ──▶ tokenize (recurse → string leaves → NFC → lower+split)
                       ──▶ frozenset of tokens
                                                    │
                                                    ▼
                              jaccard(new, each_of_last_50_by_agent)
                                                    │
                                            ≥ threshold (0.9 default)
                                                    ▼
                                          JaccardDuplicateError

    tokenize edge cases (covered by tests/unit/test_dedup.py): empty payload,
    numeric/bool/null leaves, dict keys, lowercase coercion, Korean NFC.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any, Final

# Kinds that publish must reject before storage. Heartbeats are noise.
BLOCKLISTED_KINDS: Final[frozenset[str]] = frozenset({"heartbeat", "ping", "noop"})

DEFAULT_JACCARD_THRESHOLD: Final[float] = 0.9


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _canon(obj: Any) -> Any:
    if isinstance(obj, str):
        return _nfc(obj)
    if isinstance(obj, dict):
        return {k: _canon(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_canon(v) for v in obj]
    return obj


def payload_sha256(payload: dict[str, Any]) -> str:
    """sha256 of NFC-normalized, key-sorted compact JSON."""
    canonical = json.dumps(
        _canon(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def tokenize(payload: dict[str, Any]) -> frozenset[str]:
    """Recurse into payload, collect string leaves only.

    Empty payload returns ``frozenset()``. Numeric/bool/null leaves are
    excluded. Dict keys are excluded (only values). Strings are NFC-normalized
    then lowercased + whitespace-split (Korean words pass through as-is).
    """
    tokens: set[str] = set()
    _collect_strings(payload, tokens)
    return frozenset(tokens)


def _collect_strings(node: Any, out: set[str]) -> None:
    if isinstance(node, str):
        for tok in _nfc(node).lower().split():
            if tok:
                out.add(tok)
    elif isinstance(node, dict):
        for v in node.values():
            _collect_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_strings(v, out)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard index. ``jaccard(∅, ∅) == 1.0`` (both empty = identical)."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def is_near_duplicate(
    new_tokens: frozenset[str],
    recent_token_sets: list[frozenset[str]],
    threshold: float = DEFAULT_JACCARD_THRESHOLD,
) -> bool:
    """True if any recent set scores ≥ threshold against ``new_tokens``.

    Empty ``new_tokens`` short-circuits to False — empty-payload near-dup is
    handled by the exact-hash UNIQUE constraint instead.
    """
    if not new_tokens:
        return False
    return any(jaccard(new_tokens, prior) >= threshold for prior in recent_token_sets)
