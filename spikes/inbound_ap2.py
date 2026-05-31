"""Spike B: 꼰대 inbound ap2 + x402 (pay-to-query).

꼰대 역할: 외부 query 요청자(querier)에게 narrative를 팔기 전,
ap2 IntentMandate + W3C-style PaymentRequest를 invoice로 발행하고
x402 PaymentMiddlewareASGI로 ``/query`` 엔드포인트를 게이팅한다.

흐름:

    1. POST /invoice {query="..."}
       → 200 + ap2 IntentMandate JSON + PaymentRequest JSON
         (proposal: 0.001 USDC, Base Sepolia, intent_expiry 5min)
    2. POST /query (no X-PAYMENT)
       → 402 + x402 challenge (settlement boundary)
    3. POST /query (with X-PAYMENT signed via x402, ERC-3009)
       → 200 + mock narrative (with citations)
       (step 3 requires funded Base Sepolia wallet — out of scope for spike)

Note: 본 spike는 server stack의 구조만 검증한다. Spike A에서 검증된 x402
middleware 패턴을 ``/query``에 그대로 재활용하고, ap2 invoice 발행 절반을
추가한다. on-chain 결제 확인은 동일하게 human-gated faucet 의존이라 비검증.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import uvicorn
from ap2.types.mandate import IntentMandate
from ap2.types.payment_request import (
    PaymentCurrencyAmount,
    PaymentDetailsInit,
    PaymentItem,
    PaymentMethodData,
    PaymentRequest,
)
from fastapi import FastAPI, Request
from pydantic import BaseModel
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.schemas import Network
from x402.server import x402ResourceServer


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
QUERY_PRICE_USDC = 0.001  # 0.001 USDC per query (1000 base units, 6 decimals)
INTENT_TTL_SECONDS = 300  # 5min invoice validity


# ── ap2 invoice schemas ────────────────────────────────────────────────────────


class QueryInvoiceRequest(BaseModel):
    """클라이언트가 invoice를 요청할 때 보내는 query 설명."""

    query: str
    subject_agent: str | None = None


class QueryInvoiceResponse(BaseModel):
    """ap2 IntentMandate + PaymentRequest를 묶은 invoice 응답."""

    invoice_id: str
    intent_mandate: IntentMandate
    payment_request: PaymentRequest
    pay_endpoint: str  # "POST {url} with X-PAYMENT header (x402 spec)"
    issued_at: str


def _build_ap2_invoice(query: str, subject_agent: str | None) -> QueryInvoiceResponse:
    """ap2 IntentMandate + W3C PaymentRequest 인보이스를 합성한다.

    - IntentMandate: 사람이 읽는 의도 + expiry
    - PaymentRequest: 결제 수단 / 금액 / 통화 표준 스키마
    """
    invoice_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expiry = (now + timedelta(seconds=INTENT_TTL_SECONDS)).isoformat()

    intent = IntentMandate(
        user_cart_confirmation_required=False,
        natural_language_description=(
            f"꼰대 정보통의 narrative 응답 1건 — "
            f"{(f'subject={subject_agent}, ' if subject_agent else '')}"
            f"질문: {query[:80]}{'…' if len(query) > 80 else ''}"
        ),
        merchants=["oldman_agent"],
        skus=["narrative_query_v1"],
        requires_refundability=False,
        intent_expiry=expiry,
    )

    amount = PaymentCurrencyAmount(currency="USDC", value=QUERY_PRICE_USDC)
    item = PaymentItem(
        label="narrative_query (oldman_agent)",
        amount=amount,
        refund_period=0,
    )
    details = PaymentDetailsInit(
        id=invoice_id,
        display_items=[item],
        total=item,
    )
    # x402 settlement method — supported_methods는 wallet/agent가 파싱하는 자유 문자열.
    method = PaymentMethodData(
        supported_methods="x402-exact",
        data={
            "network": EVM_NETWORK,
            "asset": USDC_BASE_SEPOLIA,
            "amount": "1000",  # 0.001 * 10^6 (USDC decimals)
            "pay_to": EVM_RECEIVE_ADDRESS,
            "scheme": "exact",
        },
    )
    pr = PaymentRequest(method_data=[method], details=details)

    return QueryInvoiceResponse(
        invoice_id=invoice_id,
        intent_mandate=intent,
        payment_request=pr,
        pay_endpoint="POST /query  (with X-PAYMENT header per x402 spec)",
        issued_at=now.isoformat(),
    )


# ── FastAPI 앱 + x402 middleware on /query ─────────────────────────────────────


app = FastAPI(title="oldman_agent inbound (Spike B)")

facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
server = x402ResourceServer(facilitator)
server.register(EVM_NETWORK, ExactEvmServerScheme())

# Same RouteConfig pattern as Spike A — only /query is gated; /invoice + /health 공개.
routes: dict[str, RouteConfig] = {
    "POST /query": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=EVM_RECEIVE_ADDRESS,
                price="$0.001",
                network=EVM_NETWORK,
            )
        ],
        mime_type="application/json",
        description="꼰대 narrative 응답 (pay-to-query). 0.001 USDC / Base Sepolia.",
    ),
}
app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/invoice", response_model=QueryInvoiceResponse)
async def issue_invoice(req: QueryInvoiceRequest) -> QueryInvoiceResponse:
    """ap2 IntentMandate + PaymentRequest 인보이스를 발행한다.

    결제는 별도 ``POST /query`` 엔드포인트에서 x402 X-PAYMENT 헤더로 진행된다.
    이 엔드포인트 자체는 무료 (인보이스 발행은 commitment 없음).
    """
    return _build_ap2_invoice(req.query, req.subject_agent)


class MockNarrativeResponse(BaseModel):
    narrative: str
    citations: list[dict[str, Any]]
    note: str


@app.post("/query", response_model=MockNarrativeResponse)
async def paid_query(req: QueryInvoiceRequest, request: Request) -> MockNarrativeResponse:
    """x402 결제 완료 후 진입. mock narrative + dummy citations.

    실제 production에서는 oldman_agent 본체의 ``execute_query`` 흐름을
    호출해 evidence + judge + render 파이프라인을 거친 narrative 반환.
    """
    return MockNarrativeResponse(
        narrative=(
            f"옛날에 {req.subject_agent or '그 친구'}가 그런 일을 했다고 들었구먼 [↑e0a1b2c3]."
            f" 자네가 물어본 '{req.query[:40]}'에 대한 답이 그거여."
        ),
        citations=[{"short_id": "e0a1b2c3", "kind": "observation"}],
        note="spike mock — 실제 evidence/judge pipeline 미연결",
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=4022)
