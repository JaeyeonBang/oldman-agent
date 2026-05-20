"""Spike A (T1): 꼰대 outbound x402 payment client.

꼰대 역할: 정보 제공자(publisher_server)에게 pay-to-share 결제 후 내용을 수령한다.
성공 시 tx hash / payment-id + 응답 본문을 출력하고 종료.

# Deviation from recon snippet:
# Canonical example uses x402HTTPClient.get_payment_settle_response() to extract
# payment info from response headers — not raw header.get("PAYMENT-RESPONSE").
# We follow the canonical pattern (x402-foundation/x402 examples/python/clients/httpx/main.py).
"""

import asyncio
import os
import sys
from urllib.parse import urlparse

import httpx
from eth_account import Account
from x402 import x402Client
from x402.http import x402HTTPClient
from x402.http.clients import x402HttpxClient
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client


def _require_env(name: str, guidance: str = "") -> str:
    """환경 변수를 읽는다. 없으면 즉시 종료."""
    value = os.environ.get(name)
    if not value:
        msg = f"[ERROR] 환경 변수 '{name}' 미설정."
        if guidance:
            msg += f" {guidance}"
        print(msg, file=sys.stderr)
        sys.exit(1)
    return value


def _check_facilitator_reachable(facilitator_url: str) -> None:
    """결제 전 facilitator 연결 가능 여부를 동기적으로 선점 검사한다.

    이른 실패(early detection) 목적: on-chain 서명/브로드캐스트 전에
    facilitator 장애를 감지해 무의미한 tx 시도를 막는다.
    """
    check_url = facilitator_url.rstrip("/") + "/supported"
    try:
        resp = httpx.get(check_url, timeout=8.0)
        # 200 또는 4xx 모두 "서버가 살아 있음"으로 간주 (schema rejection = 정상)
        if resp.status_code >= 500:
            print(
                f"[ABORT] facilitator {check_url} 응답 {resp.status_code} — 서버 장애.",
                file=sys.stderr,
            )
            sys.exit(1)
    except httpx.ConnectError as exc:
        print(
            f"[ABORT] facilitator 연결 불가 ({check_url}): {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except httpx.TimeoutException as exc:
        print(
            f"[ABORT] facilitator 응답 타임아웃 ({check_url}): {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


async def pay_and_fetch(resource_url: str, private_key: str) -> None:
    """x402 outbound 결제 후 리소스를 수령하고 결과를 출력한다."""
    facilitator_url = os.environ.get(
        "FACILITATOR_URL", "https://x402.org/facilitator"
    )

    # Pre-flight: facilitator 연결 검사
    _check_facilitator_reachable(facilitator_url)

    account = Account.from_key(private_key)

    # v2 API: x402Client + EVM signer 등록
    client = x402Client()
    register_exact_evm_client(client, EthAccountSigner(account))

    # header 파싱 헬퍼
    http_client = x402HTTPClient(client)

    path = urlparse(resource_url).path or "/"

    async with x402HttpxClient(client) as http:
        response = await http.get(resource_url)
        await response.aread()

        # payment settle response 추출 (canonical helper 사용)
        tx_info = "N/A"
        payment_response_raw = response.headers.get("PAYMENT-RESPONSE", "")
        try:
            settle = http_client.get_payment_settle_response(
                lambda name: response.headers.get(name)
            )
            settle_dict = settle.model_dump()
            tx_info = settle_dict.get("transaction", settle_dict.get("txHash", "N/A"))
            amount = settle_dict.get("amount", settle_dict.get("price", "N/A"))
        except (ValueError, AttributeError):
            amount = "N/A"

        print(
            f"[OK] status={response.status_code} path={path}"
            f" tx={tx_info} amount={amount} asset=USDC"
        )
        print(f"[BODY] {response.text}")
        print(f"[PAYMENT-RESPONSE] {payment_response_raw}")


async def main() -> None:
    """엔트리포인트."""
    private_key = _require_env(
        "EVM_PRIVATE_KEY",
        guidance=(
            "Base Sepolia 테스트 지갑 필요. 생성:\n"
            "  python3 -c \"from eth_account import Account; a=Account.create();"
            " print('KEY=', a.key.hex()); print('ADDR=', a.address)\"\n"
            "가스(ETH): https://www.alchemy.com/faucets/base-sepolia\n"
            "USDC:       https://faucet.circle.com"
        ),
    )
    resource_url = os.environ.get(
        "RESOURCE_URL", "http://localhost:4021/publish-info"
    )

    try:
        await pay_and_fetch(resource_url, private_key)
    except Exception as exc:
        print(
            f"[FAIL] {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
