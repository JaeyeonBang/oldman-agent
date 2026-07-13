"""v2 Trust Layer 완주 데모 — "동네 사랑방 제도" 한 사이클.

시나리오 (plan §3 P4 DoD):
    ① 가입     — did:key 발급 + ERC-8004 Identity 등록(mock) + 마을 명부
    ② 정직 판매 — 서명 publish → listing fee + escrow (kimbot)
    ③ 인용     — 유료 query가 인용 → royalty 해제 (조작 정보는 이 돈을 못 범)
    ④ 왜곡 적발 — canary 되사기에서 liar_bot 왜곡 3회 → honesty 추락
    ⑤ 제재     — 꾸중 → 할증 → (누적 시) 축출 + ERC-8004 Reputation 미러
    ⑥ 평판 상품 — "그놈 어때?" → 주관적 labeler narrative (citation 포함)
    ⑦ 환불     — 나쁜 정보에 당한 구매자 claim → 꼰대 판정 → 풀에서 배상

전부 결정적 (LLM/네트워크 불요). Run:
    uv run python scripts/village_demo.py
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.api.publish import execute_publish
from app.api.schemas import PublishRequest
from app.config import Settings
from app.credits.ledger import get_balance
from app.storage.db import apply_migrations, get_conn
from app.storage.identities import upsert_agent_identity
from app.storage.invoices import insert_pending_invoice, mark_invoice_settled
from app.trust.canary import judge_canary_response, plant_canary
from app.trust.erc8004 import (
    MockERC8004IdentityRegistry,
    MockERC8004ReputationRegistry,
)
from app.trust.identity import generate_identity, sign_payload
from app.trust.payout import release_royalties_for_citations
from app.trust.refund_pool import accrue_pool_fee, adjudicate_claim, file_claim
from app.trust.report import build_reputation_report
from app.trust.sanctions import apply_sanction_effects
from app.trust.service import record_trust_event

T0 = datetime(2026, 7, 13, 9, 0, 0, tzinfo=UTC)


def _banner(step: str) -> None:
    print(f"\n{'=' * 60}\n{step}\n{'=' * 60}")


async def main() -> None:
    tmp = Path(tempfile.mkdtemp()) / "village_demo.duckdb"
    conn = get_conn(str(tmp))
    apply_migrations(conn)
    settings = Settings(
        db_path=str(tmp),
        jaccard_window=50,
        jaccard_threshold=0.9,
        payment_enabled=True,
        royalty_enabled=True,
        publish_reward=5,
        query_price=3,
        refund_pool_fee=1,
        starting_grant=100,
    )
    identity_reg = MockERC8004IdentityRegistry()
    reputation_reg = MockERC8004ReputationRegistry()

    _banner("① 가입 — did:key + ERC-8004 Identity + 마을 명부 (swift trust: 잠정 허용)")
    agents: dict[str, Any] = {}
    for name in ("kimbot", "liar_bot"):
        ident = generate_identity()
        reg = identity_reg.register(
            agent_domain=f"{name}.example",
            did=ident.did,
            a2a_endpoint=f"https://{name}.example",
        )
        upsert_agent_identity(
            conn,
            agent_id=name,
            did=ident.did,
            erc8004_agent_id=reg.agent_id,
            erc8004_chain=reg.chain,
        )
        agents[name] = {"identity": ident, "erc8004_id": reg.agent_id}
        print(f"  {name}: did={ident.did[:24]}… / ERC-8004 agentId={reg.agent_id}")

    _banner("② 정직 판매 (kimbot) — 서명 publish → listing fee 즉시 + 잔액 escrow")
    kim = agents["kimbot"]["identity"]
    event_ids: list[str] = []
    for i, text in enumerate(
        ["이봇이 새 skill을 공개했다", "박봇이 약속을 지켰다", "최봇이 데이터셋을 나눴다"]
    ):
        payload = {"text": text}
        resp = await execute_publish(
            conn,
            settings,
            PublishRequest(
                event_kind="anecdote",
                source_agent="kimbot",
                observed_agent=None,
                declared_source_type="third_party",
                payload=payload,
                ts=T0 + timedelta(minutes=i),
                seller_did=kim.did,
                payload_signature=sign_payload(kim.seed_hex, payload, "kimbot"),
            ),
        )
        assert resp.event_id is not None
        event_ids.append(resp.event_id)
    print(f"  kimbot 잔고: {get_balance(conn, 'kimbot')} (listing fee 3건 즉시 지급)")
    escrow_row = conn.execute(
        "SELECT COUNT(*) FROM royalty_escrows WHERE status='open'"
    ).fetchone()
    open_escrows = escrow_row[0] if escrow_row else 0
    print(f"  open escrow: {open_escrows}건 (인용되면 지급, 조작 정보는 못 버는 돈)")

    _banner("③ 유료 query 인용 → royalty 해제")
    invoice_id = "00000000-0000-4000-8000-000000000001"
    insert_pending_invoice(
        conn,
        invoice_id=invoice_id,
        query="요즘 마을 소식 좀",
        subject_agent=None,
        intent_expiry=T0 + timedelta(days=1),
    )
    mark_invoice_settled(
        conn, invoice_id, "00000000-0000-4000-8000-00000000000a", settled_at=T0
    )
    accrue_pool_fee(conn, settings, invoice_id=invoice_id, now=T0)
    releases = release_royalties_for_citations(
        conn,
        settings,
        citation_event_ids=event_ids[:2],  # narrative가 2건 인용했다고 가정
        invoice_id=invoice_id,
        now=T0 + timedelta(hours=1),
    )
    for r in releases:
        print(f"  royalty: {r.seller_agent} +{r.amount} ({r.status}) ← [↑{r.event_id[:8]}]")
    print(f"  kimbot 잔고: {get_balance(conn, 'kimbot')}")

    _banner("④ canary 되사기 — liar_bot 왜곡 적발 (honesty 오라클)")
    truth = {"text": "김봇이 이봇에게 데이터셋을 무상 공유했다"}
    for i in range(3):
        cid = plant_canary(
            conn, topic=f"canary-{i}", answer_key=truth, now=T0 + timedelta(hours=i)
        )
        verdict = judge_canary_response(
            conn,
            canary_id=cid,
            seller_agent="liar_bot",
            response_payload={"text": "김봇이 데이터셋을 훔쳤다는 소문이야"},
            now=T0 + timedelta(hours=i),
        )
        print(
            f"  canary#{i}: match={verdict.match_score:.2f} → "
            f"{'통과' if verdict.passed else '왜곡!'} "
            f"(state={verdict.trust.state}, 위반 {verdict.trust.violation_count}회)"
        )
    # 정직 대조군
    for i in range(3):
        record_trust_event(
            conn,
            agent_id="kimbot",
            criterion="honesty",
            positive=True,
            cause="canary_pass",
            cause_ref=f"k-{i}",
            now=T0 + timedelta(hours=i),
        )

    _banner("⑤ 단계적 제재 — 꾸중 + 가격 페널티 + ERC-8004 Reputation 미러")
    directive = apply_sanction_effects(
        conn,
        agent_id="liar_bot",
        reputation_registry=reputation_reg,
        erc8004_agent_id=agents["liar_bot"]["erc8004_id"],
    )
    print(f"  상태: {directive.state} / 매입 배수 x{directive.price.buy_multiplier}")
    print(f"  꼰대: \"{directive.scold}\"")
    fb = reputation_reg.feedbacks_for(agents["liar_bot"]["erc8004_id"])[0]
    print(f"  ERC-8004 giveFeedback 발행: score={fb.score}, tag={fb.tag} (produce-only)")

    _banner("⑥ 평판 상품 — oldman.intent=reputation")
    for name in ("kimbot", "liar_bot", "stranger_bot"):
        report = build_reputation_report(conn, subject_agent=name)
        print(f"\n  Q: {name} 어때?\n  꼰대: {report.text}")

    _banner("⑦ 환불 풀 — 나쁜 정보 배상 (꼰대가 claims adjudicator)")
    claim_id = file_claim(
        conn,
        claimant_agent="querier_zed",
        invoice_id=invoice_id,
        reason_text="산 narrative가 이후 사료와 모순됨",
        now=T0 + timedelta(days=1),
    )
    decision = adjudicate_claim(
        conn, settings, claim_id=claim_id, justified=True, now=T0 + timedelta(days=1)
    )
    print(f"  claim {decision.status}: querier_zed에게 {decision.payout} 배상")
    print(f"  querier_zed 잔고: {get_balance(conn, 'querier_zed')}")

    _banner("⑧ 회계 감사 — 자산 보존 invariant (돈이 새지 않았는가)")
    from app.credits.audit import audit_credits

    audit = audit_credits(conn)
    print(
        f"  Σ잔고={audit.total_balance} == Σ발행={audit.total_minted} "
        f"→ {'OK' if audit.balanced else 'MISMATCH!'}"
    )
    print(f"  open escrow 부채: {audit.open_escrow_liability} / issues: {audit.issues}")

    conn.close()
    if not audit.balanced or audit.issues:
        raise SystemExit("❌ 회계 감사 실패")
    print("\n✅ 완주 — 신뢰 메커니즘 8단계 전부 작동 (결정적, LLM/체인 불요)")


if __name__ == "__main__":
    asyncio.run(main())
