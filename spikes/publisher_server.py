"""Spike A (T1): 정보 제공자 서버 — pay-to-share 엔드포인트.

꼰대(outbound_x402.py)의 결제를 받아 정보를 돌려준다.
x402 PaymentMiddlewareASGI로 /publish-info 엔드포인트를 보호한다.

Note (spike only): EVM_RECEIVE_ADDRESS와 EVM_PRIVATE_KEY가 같은 지갑이어도 동작한다.
  (자기 자신에게 결제 → Base Sepolia gas만 소모) 프로덕션에서는 다른 지갑을 사용할 것.
"""

import os
import sys

import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.schemas import Network
from x402.server import x402ResourceServer

# ── 환경 변수 ──────────────────────────────────────────────────────────────────

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"[ERROR] 환경 변수 '{name}' 미설정.", file=sys.stderr)
        sys.exit(1)
    return value


EVM_RECEIVE_ADDRESS: str = _require_env("EVM_RECEIVE_ADDRESS")
EVM_NETWORK: Network = "eip155:84532"  # Base Sepolia
FACILITATOR_URL: str = os.environ.get(
    "FACILITATOR_URL", "https://x402.org/facilitator"
)

USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

# ── 스키마 ─────────────────────────────────────────────────────────────────────

class PublishInfoResponse(BaseModel):
    received: bool
    echo: dict[str, str]


# ── FastAPI 앱 ─────────────────────────────────────────────────────────────────

app = FastAPI(title="oldman_agent publisher (spike)")

# x402 미들웨어 설정
facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
server = x402ResourceServer(facilitator)
server.register(EVM_NETWORK, ExactEvmServerScheme())

# 0.001 USDC = 1000 (6 decimals)
routes: dict[str, RouteConfig] = {
    "GET /publish-info": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=EVM_RECEIVE_ADDRESS,
                price="$0.001",
                network=EVM_NETWORK,
            )
        ],
        mime_type="application/json",
        description="꼰대 정보 구매 (pay-to-share). 0.001 USDC / Base Sepolia.",
    ),
}

app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check() -> dict[str, str]:
    """상태 확인 (결제 불필요)."""
    return {"status": "ok"}


@app.get("/publish-info", response_model=PublishInfoResponse)
async def publish_info(request: Request) -> PublishInfoResponse:
    """결제 완료 후 접근 가능한 정보 엔드포인트."""
    # request.headers에서 클라이언트 정보 에코
    user_agent = request.headers.get("user-agent", "unknown")
    return PublishInfoResponse(
        received=True,
        echo={"user_agent": user_agent, "path": str(request.url.path)},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=4021)
