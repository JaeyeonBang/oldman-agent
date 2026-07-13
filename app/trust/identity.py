"""did:key(ed25519) identity — 발급/서명/검증.

publish payload 서명이 citation ``[↑eXX]``에 "누가 판 정보인가"의 암호학적
증명을 부여한다 (P0). did:key = ``did:key:z`` + base58btc(0xed01 ∥ pubkey32).

didkit 대신 pynacl 직접 구현 — P0에는 VC 발급이 불필요하고, 필요한 것은
"임의 payload에 대한 ed25519 raw 서명"뿐 (plan §Phase0 폴백 경로를 기본 채택).
서명 대상은 ``payload_sha256(payload)`` — dedup과 동일한 canonical 해시라
서명이 dedup identity와 정확히 같은 바이트에 바인딩된다.
"""

from __future__ import annotations

import base64
import unicodedata
from dataclasses import dataclass
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from app.storage.dedup import payload_sha256

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ED25519_MULTICODEC = b"\xed\x01"
_DID_KEY_PREFIX = "did:key:z"


class InvalidDidError(ValueError):
    """did:key(ed25519) 형식이 아니거나 디코딩 불가."""


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    chars: list[str] = []
    while n:
        n, rem = divmod(n, 58)
        chars.append(_B58_ALPHABET[rem])
    pad = len(data) - len(data.lstrip(b"\x00"))
    return "1" * pad + "".join(reversed(chars))


def _b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        idx = _B58_ALPHABET.find(ch)
        if idx < 0:
            raise InvalidDidError(f"invalid base58 char: {ch!r}")
        n = n * 58 + idx
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + body


@dataclass(frozen=True)
class AgentIdentity:
    """seed_hex는 비밀키 — 로그/응답에 노출 금지."""

    did: str
    seed_hex: str


def generate_identity() -> AgentIdentity:
    sk = SigningKey.generate()
    return AgentIdentity(
        did=did_from_public_key(bytes(sk.verify_key)),
        seed_hex=bytes(sk).hex(),
    )


def did_from_seed(seed_hex: str) -> str:
    """32-byte seed hex → did:key (동일 seed는 항상 동일 DID)."""
    sk = SigningKey(bytes.fromhex(seed_hex))
    return did_from_public_key(bytes(sk.verify_key))


def did_from_public_key(public_key: bytes) -> str:
    return _DID_KEY_PREFIX + _b58encode(_ED25519_MULTICODEC + public_key)


def public_key_from_did(did: str) -> bytes:
    if not did.startswith(_DID_KEY_PREFIX):
        raise InvalidDidError(f"not a did:key with multibase 'z': {did!r}")
    raw = _b58decode(did[len(_DID_KEY_PREFIX) :])
    if len(raw) != 34 or raw[:2] != _ED25519_MULTICODEC:
        raise InvalidDidError("not an ed25519 did:key (need 0xed01 + 32-byte key)")
    return raw[2:]


def _signing_message(payload: dict[str, Any], source_agent: str) -> bytes:
    """서명 대상 = payload canonical 해시 + source_agent(결제 수취자).

    payload 해시만 서명하면 서명이 '무엇을'만 증명하고 '누가 파는가'는 증명하지
    못해, 캡처된 서명을 다른 source_agent로 재제출하는 결제 하이재킹이 가능하다
    (H1). source_agent를 바인딩해 서명을 판매 행위 주체에 묶는다. 해시는 고정
    길이(64 hex)라 ``<hash>|<agent>`` 구분자 결합이 모호하지 않다. source_agent는
    NFC 정규화 — payload 해시의 canonical 정책과 일관.
    """
    normalized = unicodedata.normalize("NFC", source_agent)
    return f"{payload_sha256(payload)}|{normalized}".encode()


def sign_payload(seed_hex: str, payload: dict[str, Any], source_agent: str) -> str:
    """(payload canonical 해시 + source_agent)에 대한 ed25519 서명 (base64)."""
    sk = SigningKey(bytes.fromhex(seed_hex))
    msg = _signing_message(payload, source_agent)
    return base64.b64encode(sk.sign(msg).signature).decode("ascii")


def verify_payload(
    did: str, payload: dict[str, Any], signature_b64: str, source_agent: str
) -> bool:
    """검증 실패는 raise가 아니라 False — publish 경로에서 도메인 에러로 매핑.

    서명은 payload와 source_agent 양쪽에 바인딩 — source_agent가 다르면 실패.
    """
    try:
        pub = public_key_from_did(did)
        sig = base64.b64decode(signature_b64.encode("ascii"), validate=True)
        VerifyKey(pub).verify(_signing_message(payload, source_agent), sig)
        return True
    except (InvalidDidError, BadSignatureError, ValueError, TypeError):
        return False
