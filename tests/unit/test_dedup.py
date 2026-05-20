"""Phase 1.4 RED: dedup primitives (T3 edge cases included)."""

from __future__ import annotations

import unicodedata

from app.storage.dedup import (
    BLOCKLISTED_KINDS,
    is_near_duplicate,
    jaccard,
    payload_sha256,
    tokenize,
)


def test_blocklist_contains_heartbeat() -> None:
    assert "heartbeat" in BLOCKLISTED_KINDS


def test_tokenize_nested_strings_and_lists() -> None:
    payload = {"text": "hello world", "tags": ["alpha", "beta gamma"]}
    assert tokenize(payload) == frozenset({"hello", "world", "alpha", "beta", "gamma"})


def test_tokenize_empty_payload_returns_empty_set() -> None:
    assert tokenize({}) == frozenset()


def test_tokenize_korean_text_preserves_words() -> None:
    assert tokenize({"text": "꼰대 정보통"}) == frozenset({"꼰대", "정보통"})


def test_tokenize_numeric_leaves_excluded() -> None:
    assert tokenize({"count": 42, "score": 3.14}) == frozenset()


def test_tokenize_boolean_and_null_excluded() -> None:
    assert tokenize({"flag": True, "other": False, "x": None}) == frozenset()


def test_tokenize_dict_keys_not_included() -> None:
    assert tokenize({"hello": "world"}) == frozenset({"world"})


def test_tokenize_lowercases_strings() -> None:
    assert tokenize({"x": "ABC DeF"}) == frozenset({"abc", "def"})


def test_jaccard_identical() -> None:
    s = frozenset({"a", "b", "c"})
    assert jaccard(s, s) == 1.0


def test_jaccard_disjoint() -> None:
    assert jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0


def test_jaccard_boundary_0_9() -> None:
    c = frozenset({f"t{i}" for i in range(10)})
    d = frozenset({f"t{i}" for i in range(9)})
    assert jaccard(c, d) == 0.9


def test_jaccard_both_empty_returns_1() -> None:
    assert jaccard(frozenset(), frozenset()) == 1.0


def test_is_near_duplicate_empty_new_tokens_returns_false() -> None:
    assert is_near_duplicate(frozenset(), [frozenset({"a", "b"})], threshold=0.9) is False


def test_is_near_duplicate_finds_match() -> None:
    new = frozenset({f"t{i}" for i in range(10)})
    prior = frozenset({f"t{i}" for i in range(10)})
    assert is_near_duplicate(new, [prior], threshold=0.9) is True


def test_is_near_duplicate_below_threshold_returns_false() -> None:
    new = frozenset({"alpha", "beta", "gamma", "delta"})
    prior = frozenset({"omega"})
    assert is_near_duplicate(new, [prior], threshold=0.9) is False


def test_payload_sha256_canonical_key_order_invariant() -> None:
    assert payload_sha256({"a": 1, "b": 2}) == payload_sha256({"b": 2, "a": 1})


def test_payload_sha256_unicode_normalization_nfc() -> None:
    composed = "꼰대"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    assert payload_sha256({"text": composed}) == payload_sha256({"text": decomposed})


def test_payload_sha256_empty_payload_is_stable() -> None:
    assert payload_sha256({}) == payload_sha256({})
