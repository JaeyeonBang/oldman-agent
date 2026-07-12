"""P0 trust identity — did:key 발급/서명/검증 (TDD RED → GREEN).

did:key(ed25519) 스펙: 'did:key:z' + base58btc(0xed 0x01 + pubkey 32B).
서명은 payload_sha256(payload) hex digest bytes에 대한 ed25519 raw 서명 (base64).
"""

from __future__ import annotations

import pytest

from app.trust.identity import (
    InvalidDidError,
    generate_identity,
    public_key_from_did,
    sign_payload,
    verify_payload,
)


def test_generate_identity_did_format() -> None:
    ident = generate_identity()
    # ed25519 multicodec(0xed01) → base58btc는 항상 'z6Mk'로 시작
    assert ident.did.startswith("did:key:z6Mk")
    assert len(ident.seed_hex) == 64  # 32-byte seed hex


def test_did_public_key_roundtrip() -> None:
    ident = generate_identity()
    pub = public_key_from_did(ident.did)
    assert isinstance(pub, bytes)
    assert len(pub) == 32


def test_two_identities_are_distinct() -> None:
    a, b = generate_identity(), generate_identity()
    assert a.did != b.did
    assert a.seed_hex != b.seed_hex


def test_sign_and_verify_ok() -> None:
    ident = generate_identity()
    payload = {"text": "김봇이 이봇에게 사과했다", "topic": "화해"}
    sig = sign_payload(ident.seed_hex, payload)
    assert verify_payload(ident.did, payload, sig) is True


def test_verify_is_key_order_invariant() -> None:
    """canonical JSON 서명 — dict 키 순서가 달라도 같은 payload면 검증 통과."""
    ident = generate_identity()
    sig = sign_payload(ident.seed_hex, {"a": 1, "b": "x"})
    assert verify_payload(ident.did, {"b": "x", "a": 1}, sig) is True


def test_tampered_payload_fails() -> None:
    ident = generate_identity()
    sig = sign_payload(ident.seed_hex, {"text": "원본"})
    assert verify_payload(ident.did, {"text": "변조"}, sig) is False


def test_wrong_did_fails() -> None:
    signer, other = generate_identity(), generate_identity()
    payload = {"text": "원본"}
    sig = sign_payload(signer.seed_hex, payload)
    assert verify_payload(other.did, payload, sig) is False


def test_garbage_signature_fails() -> None:
    ident = generate_identity()
    assert verify_payload(ident.did, {"text": "x"}, "bm90LWEtc2ln") is False


@pytest.mark.parametrize(
    "bad_did",
    [
        "did:web:example.com",
        "did:key:abc",  # multibase 'z' prefix 아님
        "did:key:z" + "1" * 10,  # 잘못된 multicodec/length
        "",
    ],
)
def test_invalid_did_raises(bad_did: str) -> None:
    with pytest.raises(InvalidDidError):
        public_key_from_did(bad_did)
