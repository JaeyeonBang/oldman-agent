# 에이전트 신뢰성 판별 방안 — 종합 리서치 (2026-07-12)

> 목적: A2A 생태계에서 "이 에이전트를 믿어도 되는가?"를 판별하는 모든 주요 방안(ERC-8004, NFT/SBT, 평판 시스템, 블록체인, DID/VC, TEE 등)을 검토하고, oldman_agent에 적용할 구체적 개발 방안을 도출한다.
> 방법: 6개 병렬 리서치 트랙(ERC-8004 / A2A·AP2·x402 네이티브 / DID·VC / 평판 시스템 / TEE·검증 실행 / NFT·SBT·Web-of-Trust) + 종합 + devil's advocate 검증. 모든 주장에 출처 URL 첨부. AI 리서치 도구(병렬 서브에이전트 + 웹 검색) 사용.
> **후속 문서**: `research/agent-trust-impl-plan-2026-07.md` — 2차 리서치(메커니즘 디자인·능동 검증·제도 거버넌스) + 통합 종합 + 구현 plan. 본 문서 §4.2의 corroboration 오라클은 후속 문서 §2.2에서 surprise-가중으로 정교화됨.

---

## 0. Executive Summary

**결론 먼저: "신뢰"는 단일 기술로 해결되지 않는다. 프로토콜 스택(A2A+AP2+x402)은 "누가 말했고 돈이 움직였는가"까지만 보증하고, "말한 내용이 참인가"는 비어 있다. 그 빈칸이 바로 oldman_agent의 제품이다.**

6개 트랙의 수렴 결론:

1. **서명된 identity는 필수·저비용** — JWS-서명 AgentCard 또는 did:key. 모든 신뢰 메커니즘의 전제 조건이며 하루면 붙는다.
2. **온체인 평판(ERC-8004)은 표준으로서 유망하나 실증적으로 아직 깨져 있다** — 2026-05 기준 등록의 85~97%가 placeholder, 리뷰어의 59~91%가 sybil 패턴 [arXiv 2606.26028]. "온체인이니까 신뢰 가능"은 성립하지 않는다.
3. **소규모 네트워크(5-20)에서는 글로벌 평판 점수가 아니라 주관적(local) 신뢰 + 거래-게이팅 + 객관 신호가 정답** — Beta/Subjective Logic 코어 + "결제한 자만 평가" + citation grounding을 오라클로.
4. **경제적 담보(stake/bond)는 평판이 못 막는 구멍(sybil, value-imbalance)을 막는다** — x402 결제 레일이 이미 있으므로 한 발짝이면 된다.
5. **TEE attestation은 2026년 현재 프로덕션 수준·저비용(3-8% 오버헤드, 월 $5-20)이지만, "어떤 코드가 돌았는가"만 증명하고 "출력이 정직한가"는 증명 못 한다.**
6. **NFT는 평판에 부적합(양도 가능 = 부의 증명이지 신뢰의 증명이 아님), SBT는 개념은 옳으나 이 규모에선 과잉.** 가져갈 원칙은 하나: **평판은 양도 불가능해야 한다.**

**oldman_agent 관점의 핵심 통찰: 꼰대는 신뢰 인프라의 소비자가 아니라 공급자다.** 동네 사랑방은 원래 "저 집 아들 믿을 만한가?"를 답해주는 곳이다. 신뢰 리서치의 결론은 곧 **꼰대의 새 상품 라인 — 평판 narrative(pay-to-query의 신규 intent)** 설계도가 된다. 단, devil's advocate 검증(§5)이 강제한 두 전제를 붙인다: ① 꼰대의 평판 발화는 정본(canonical) 점수가 아니라 **주관적 label**이다 — Bluesky labeler 모델이며, 꼰대 페르소나("내가 보기엔 그 놈은…")가 바로 이 주관성의 정직한 UI다. ② 자가 운영 5-20 데모에는 실제 적대자가 없으므로 이것은 **신뢰 메커니즘의 시연(trust-mechanics demo)**이지 라이브 신뢰 시스템이 아니다. 상세 로드맵은 §4.

---

## 1. 문제 정의: "신뢰"의 6계층 프레임

"에이전트를 신뢰한다"는 말은 최소 여섯 개의 서로 다른 질문을 뭉뚱그린 것이다. Hu et al.의 inter-agent trust 분류 [arXiv 2511.03434]를 빌리면:

| 계층 | 질문 | 담당 기술 | 상태 (2026) |
|---|---|---|---|
| **Brief** (자기소개) | 너는 누구인가? | AgentCard, DID | 성숙 (단, 서명은 optional) |
| **Claim** (주장) | 너는 무엇을 할 수 있다고 주장하는가? | AgentCard skills, 모델 카드 | 성숙하나 자기-신고 |
| **Proof** (증명) | 주장을 암호학적으로 증명할 수 있는가? | TEE attestation, zkML, VC | TEE만 실용 단계 |
| **Stake** (담보) | 거짓이면 무엇을 잃는가? | staking/slashing, escrow, bond | 메커니즘 성숙, 에이전트 적용 초기 |
| **Reputation** (평판) | 과거에 어떻게 행동했는가? | 평판 시스템, ERC-8004 Reputation | 이론 성숙, 온체인 실증은 실패 중 |
| **Constraint** (구속) | 잘못하면 무엇으로 제어되는가? | mandate(AP2), scope 제한, 법 | AP2가 결제 영역에서 해결 |

같은 논문의 권고: **Proof + Stake를 앵커로, Brief(서명 identity)는 발견용, Reputation은 soft overlay로만.** Claim-only(AgentCard)와 Reputation-only는 prompt injection·sycophancy·hallucination 같은 LLM 고유 실패 모드에 취약하다.

또 하나의 축 — **무엇에 대한 신뢰인가**:
- **identity 신뢰**: 사칭이 아닌가 → 서명으로 해결됨
- **결제 신뢰**: 돈을 떼먹지 않는가 → x402/AP2가 해결함
- **행위 신뢰**: 약속한 코드를 실행했는가 → TEE가 부분 해결
- **내용 신뢰**: 판 정보가 참인가 → **어떤 프로토콜도 해결 못 함. 애플리케이션 레이어의 몫.**

> "Authenticity is not correctness." — 서명은 발화자를 확정할 뿐, 발화의 진위는 확정하지 않는다. [https://www.arunbaby.com/ai-security/0004-agent-to-agent-trust-how-multi-agent-systems-authenticate-each-other/]

---

## 2. 방안별 검토

### 2.1 ERC-8004 "Trustless Agents"

**무엇인가**: A2A 위에 올리는 온체인 신뢰 레이어. 체인당 싱글톤 컨트랙트 3개 — Identity(ERC-721 기반, agentId=tokenId, agentURI→등록 파일), Reputation(`giveFeedback(agentId, score 0-100, ...)`, 서명된 `feedbackAuth`로 사전 승인된 클라이언트만 피드백 가능), Validation(`validationRequest`/`validationResponse`, TEE·zkML·재실행 검증을 플러그인처럼). 온체인에는 포인터+해시만, 무거운 데이터는 IPFS/HTTPS. [https://eips.ethereum.org/EIPS/eip-8004]

**현황**: 2025-08 초안 → 2026-01-29 레퍼런스 레지스트리 이더리움 메인넷 배포. 저자: MetaMask·EF dAI팀·Google·Coinbase. 공식 문서상 스테이터스는 여전히 Draft/Review 단계 (메인넷 배포 ≠ EIP Final). 최대 변경: 커스텀 identity → 표준 ERC-721로 재설계. ~21k 에이전트 등록 (헤드라인 숫자). [https://github.com/erc-8004/erc-8004-contracts]

**실증 비판 (가장 중요)**: arXiv 2606.26028 "Can Trustless Agents Be Trusted?" (Ethereum/BSC/Base, ~2026-05):
- 유효한 등록 파일 + 살아있는 endpoint를 가진 등록: **3% / 4% / 15%** — 나머지는 placeholder
- 리뷰어의 **73.6% / 59.2% / 90.6%가 조직적 sybil 패턴**
- "Reputation Registry는 현재 신뢰 신호로 기능할 수 없다 — 값이 비교 불가능하고, 검증 가능한 상호작용에 근거하지 않으며, 최소 비용으로 조작 가능"

`feedbackAuth`는 *무단* 피드백만 막을 뿐, 자기 거래 링(self-dealing ring)의 피드백 farming은 못 막는다. Validator 경제학(담보/보상/슬래싱)은 스펙 미정의.

**Python 경로**: `erc-8004-py` (PyPI) + `web3.py` + 공식 `a2a-python`. BNB Agent SDK는 testnet 가스비 무료 등록 지원. [https://libraries.io/pypi/erc-8004-py]

**판정**: 표준 방향은 맞고 A2A·x402와의 합성 설계도 깔끔하다. 그러나 **지금 신뢰 판별기로 쓰기엔 평판 레이어가 실증적으로 무의미**하다. 5-20 에이전트 자가 운영 데모에는 선택적 장식(Identity Registry testnet 등록 정도) 이상의 가치가 없다. 표준 추적은 유지.

### 2.2 A2A / AP2 / x402 네이티브 신뢰

**A2A**: AgentCard는 JWS(RFC 7515) 서명 *가능*하나 서명은 MAY이고 검증 방법은 미규정 — 미서명 카드 스푸핑이 "저비용 공격"으로 지목됨 [https://semgrep.dev/blog/2025/a-security-engineers-guide-to-the-a2a-protocol/]. 인증은 OAuth2/OIDC/mTLS에 위임. 레지스트리 API는 미표준 — MCP Registry, AGNTCY(Linux Foundation, IPFS DHT+Sigstore), MS Entra Agent ID(→Agent 365), MIT NANDA 등 5개 모델이 경쟁·연합 중 [arXiv 2508.03095]. v1.0 stable (2026-04)에서 signed cards + AP2 extension 공식화.

**AP2**: W3C VC 기반 mandate 3종(Intent/Cart/Payment)의 부모-자식 체인으로 **위임의 부인 방지(non-repudiation)** 를 해결. 사용자 의도가 암호학적으로 서명되어 에이전트가 위조 불가. 단, 이것은 **권한·책임 모델이지 품질·정직성 모델이 아니다.** [https://ap2-protocol.org/topics/core-concepts/]

**x402**: **결제 신뢰**를 해결 — 모든 페이로드가 buyer-서명 + 온체인 정산이라 악의적 facilitator도 buyer 의도 밖으로 자금 이동 불가. 2026-04 기준 ~69k 에이전트, ~165M tx. 그러나 **"낙관적 정산(optimistic settlement) — 실행 증명 없이 결제"**: 판매자가 물건(정보)을 제대로 줬는지는 전혀 보증 안 함 [arXiv 2602.00213].

**판정**: 스택은 "누가, 얼마나, 누구 허락으로"를 다 풀었고 **"내용이 참인가"만 안 풀었다.** oldman_agent의 validator.py(citation grounding)와 inline citation 강제는 프로토콜이 punt한 지점을 애플리케이션 레이어에서 메우는 구조 — **이 격차가 곧 제품 차별화 지점이다.**

### 2.3 DID / VC / Trust Registry / Know-Your-Agent

**표준 동향**: DIF·ToIP가 2025 말 "Trusted AI Agents" WG 공동 출범. Vouched가 MCP-I(→KYA-OS)를 2026-03 DIF에 기증. 수렴 패턴은 **3계층 credential 모델** — ① agent DID ② 인간/조직 principal을 잇는 VC ③ 범위 제한 delegation credential. [https://identity.foundation/working-groups/trusted-agents.html]

**Trust registry**: ToIP TRQP v2.0("trust 도메인의 DNS" — "entity X가 거버넌스 Z 하에 권한 Y를 갖는가?" 조회), OpenID Federation(계층적 trust chain), eIDAS 2.0/EUDI(법적 앵커, 에이전트 적용은 whitepaper 단계).

**KYA 상용화**: Trulioo "Digital Agent Passport", cheqd(DID-linked agent passport + trust registry), AstraSync, Nuggets 등 — agentic commerce가 견인. 오픈소스 유사체 Agent Passport System(APS)은 **서명된 accountability receipt**(ActionReceipt 등) 개념이 oldman_agent의 event store·citation 모델과 구조적으로 유사.

**위임 체인 기술**: 실용 계열(OAuth RFC 8693 token exchange, GNAP RFC 9635) vs 검증 계열(UCAN, Biscuit, ZCAP-LD). 에이전트용 IETF 드래프트 다수, 확정 없음.

**Python 실현성**: `didkit`(SpruceID, PyPI) — did:key 생성 + VC 발급/검증. did:key는 호스팅 불필요(데모 최적), did:web은 도메인 필요·복잡도만 추가. ACA-Py/eIDAS급 SSI 인프라는 이 규모에 명백한 과잉. **"DID가 '서명된 JWT + allow-list'로 안 되는 무엇을 해결하는가?"를 계속 물어라.**

**판정**: 신뢰의 **Brief 계층을 가장 표준적으로** 채우는 길. 최소 구성(did:key + 거래를 DID에 바인딩하는 서명 VC)은 didkit으로 ~1일. citation `[↑e42]`에 "누가 이 정보를 팔았고 팔 권한이 있었는가"의 검증 가능한 증명을 붙일 수 있다.

### 2.4 평판 시스템 (고전 MAS → LLM 에이전트 사회)

**고전 모델 요약**:

| 모델 | 핵심 | 5-20 에이전트 적용성 |
|---|---|---|
| EigenTrust (2003) | 신뢰 행렬의 고유벡터 = 글로벌 전이 신뢰 | **부적합** — 수백+ 규모용, sybil-proof 아님, pre-trusted peer가 단일 실패점 |
| Beta / Subjective Logic (Jøsang) | (긍정,부정) 카운트의 Beta 분포, **불확실성이 1급 시민** | **최적** — 신규=("불신"이 아니라 "미지"), cold-start 자연 해결, 해석 가능 |
| PeerTrust (2004) | 평가자의 신뢰도로 평가를 가중 | 아이디어만 차용 |
| FIRE (2006) | 직접+역할+증인+**인증(휴대) 평판** | 인증 평판 = cold-start 해법, ERC-8004 Reputation의 조상 |
| ReGreT (2001) | **다기준 분해** (납기 vs 품질) | 차용 — "결제 이행"과 "정보 정확성"을 분리 |
| TRAVOS (2006) | **증인의 과거 보고 정확도로 증인을 할인** | **매우 높음** — "정보가 상품"인 네트워크의 핵심 방어 |

**공격 분류와 완화**:

| 공격 | 완화 |
|---|---|
| Sybil (가짜 다수) | identity 비용 부과(stake), 거래-게이팅, 신규는 0 가중 시작. **순수 평점 시스템은 증명 가능하게 sybil-proof 불가** |
| Whitewashing (재가입 세탁) | 신규를 낮음+고불확실성으로 시작 (중립 금지), 재진입 비용 |
| Collusion / ballot-stuffing | 거래-게이팅(평가에 실제 결제 필요), pair별 평가 상한, 상호평가 클러스터 탐지 |
| Bad-mouthing (경쟁자 음해) | 부정 평가도 거래-백킹 요구, TRAVOS식 증인 필터 |
| On-off (선행 후 배신) | **비대칭 동역학 — 느리게 오르고 빠르게 떨어짐**, 위반 이력 기반 회복 비용 |
| Value imbalance (소액 신뢰→고액 배신) | **거래액 가중 평판** + 고액 구간은 escrow/bond |

**시장 실증 교훈**: 인간 마켓플레이스 평점은 구조적으로 인플레이션된다(Airbnb 평균 ~4.7, Uber 90%가 만점 — 보복 두려움에 의한 부정 평가 억제) [Tadelis, Annual Review]. 검증된 해독제는 **Verified Purchase — 거래-게이팅된 평가**. AI 에이전트 마켓(Virtuals/Fetch/Olas)은 현재 평점이 아니라 **토큰 스테이킹**이 사실상의 신뢰 레이어.

**암호경제적 신뢰**: 평점은 이력에서 신뢰를 *추론*하고, 담보는 신뢰를 *제조*한다. staking/slashing(Kleros), optimistic oracle(UMA — 정직하면 싸고 분쟁 시만 비쌈), escrow. **담보가 이기는 조건**: 고액·일회성 거래, 객관 판정 가능한 결과, 값싼 identity. **평점이 이기는 조건**: 다수·저액·주관 품질. → **"꼬리(저액 다수)는 평점, 머리(고액 소수)는 담보"로 합성.**

**LLM 특화 신호**: LLM-as-judge는 단독 심판으로 부적합(어려운 케이스 ~25% 선호 뒤집힘). **가장 강한 객관 신호는 citation grounding** — 주장이 인용 출처에 실제로 근거하는지는 기계 검증 가능하고 여론 조작이 안 통한다. RepuNet [arXiv 2505.05029] — 직접 경험 + 간접 gossip의 2단 평판으로 착취자 고립 — 이 oldman_agent와 가장 가까운 선행 연구. gossip 기반 협력 유지 연구에서도 에이전트들이 긍정 gossip을 선호(인플레 위험)함이 관찰됨 [arXiv 2602.07777].

### 2.5 TEE / 검증 가능 실행

**하드웨어 attestation**: Intel TDX / AMD SEV-SNP / AWS Nitro / NVIDIA H100 CC 모두 프로덕션. 원리: 하드웨어 root-of-trust가 부팅 시 코드 measurement를 서명 → 원격 검증자가 벤더 루트 CA 체인 + 기대 해시 대조. **오버헤드 3-8%** (Llama-3.1-70B에서 4.7%).

**에이전트 특화 플랫폼**: **Phala dstack**이 가장 성숙 — docker-compose 그대로 배포, 이미지 해시+환경변수를 바인딩한 attestation + TEE-파생 sealed key, FastAPI Python 스타터 존재, **월 $5-20**. ElizaOS의 TEE 플러그인도 dstack 기반 — 에이전트 프레임워크 레이어의 사실상 표준. Oasis ROFL 메인넷(2025-07), Marlin/Automata는 온체인 검증 지향.

**검증 가능 추론 성숙도**: TEE(프로덕션) > opML/재실행(사용 가능, 챌린지 지연) > 암호경제 재실행(중간 스테이크용) ≫ zkML(**LLM엔 연구 단계** — 분 단위 증명 시간). 참고: temperature-0 비결정성은 batch-invariant kernel로 사실상 해결(비트 동일 재현, 처리량 ~34% 손실) — 재실행 검증이 이제 기술적으로 가능은 함.

**근본 한계 (정직한 프레이밍)**:
1. **TEE는 "어떤 코드가 돌았나"를 증명하지, 코드/모델이 정직한지·출력이 좋은지는 증명 못 한다.** enclave는 prompt-injection된 지시도 충실히 실행한다. oldman_agent에 적용하면: TEE는 validator.py가 무변조로 돌았음은 증명해도, validator가 놓친 hallucination까지는 못 잡는다.
2. TEE.Fail(2025-10) — 물리적 DDR5 interposer로 attestation 키 추출. 원격 운영자 위협 모델에는 유효, 물리 공격자에겐 한계.
3. 실무 합의: attestation은 "운영자를 믿어라"를 "하드웨어 벤더 + 공개된 코드 해시를 믿어라"로 **치환**하는 것 — 신뢰 가정의 실질 감소이지, 정직성의 증명이 아님.

**판정**: "꼰대의 narrative는 공개된 프롬프트/코드의 무변조 산출물"임을 증명하는 **서명 파이프라인**(코드 해시 공개 + TEE-sealed key로 응답 서명)은 월 $5-20에 가능. 데모 후반 단계의 차별화 요소로 적합, 필수는 아님.

### 2.6 NFT / SBT / EAS / Web-of-Trust

**NFT(양도 가능)는 평판에 구조적으로 부적합**: 양도 가능한 "평판 NFT"는 실력이 아니라 구매력을 증명한다(identity-selling 문제). ERC-6551 token-bound account나 Virtuals의 에이전트 NFT는 암호학적 연속성·자산 보유는 검증하지만, 오프체인 모델의 능력·정직성에 대해선 아무 말도 못 한다 — **verify가 아니라 brand**.

**SBT(양도 불가)**: DeSoc 논문의 통찰은 유효 — 평판 판매를 "개인키 판매"라는 신뢰 불가·처벌 가능 행위로 격하시킨다. 그러나 영구 부정 낙인·프라이버시 문제가 있고, 에이전트 간 sybil은 여전히 못 막는다. **이 규모에선 토큰 없이 원칙만 가져간다: 평판은 양도 불가능해야 한다.**

**EAS/attestation 레이어**: 스키마 기반 서명 주장("검증자 Z가 X의 작업 Y를 확인함")은 이동 가능한 평판의 *올바른 형태*. 단, attestation의 가치는 attester의 신뢰도만큼 — 질문이 "점수가 진짜인가"에서 "서명자를 믿는가"로 이동할 뿐이며, **그 질문에 답하는 것이 web-of-trust다.**

**Web-of-Trust 교훈**: PGP의 실패 원인 = 글로벌·수동·의미 모호한 신뢰 그래프는 스케일하지 않는다(GnuPG 2.2.17에서 WoT 처리 제거). 현대적 계승은 (a) trust-on-first-use + transparency log, (b) **주관적/로컬 신뢰** — 내 관점에서 검증한 피어를 통해 바깥으로 흐르는 신뢰. **Bluesky의 stackable moderation/labeler 패턴이 직접 복사할 만한 모델**: 신뢰 = 각자가 구독하는 label 소스들의 집합이지, 하나의 정본 점수가 아니다. 주관적 신뢰는 소규모에서 오히려 강하다 — 신뢰 피어가 보증하지 않는 sybil은 자기들끼리 아무리 attestation을 찍어도 내 관점에서 ~0점.

**"proof of agenthood"는 미해결 open problem** — 생체 기반 proof-of-personhood는 에이전트에 이전 불가; 대안(모델 지문, 운영자 attestation, 담보)만 제안 단계 [arXiv 2604.23280].

---

## 3. 종합: 무엇이 진짜 신호인가

여섯 트랙의 결론은 일관되게 같은 곳을 가리켰다 (주의: 하나의 질문 프레이밍에서 출발한 병렬 조사이므로 "독립 증인" 수준의 교차 검증은 아니다 — §5 M4):

1. **거래-백킹이 여론을 이긴다.** 평가 권한을 실제 결제에 게이팅하는 것(Verified Purchase 원리)이 sybil·ballot-stuffing·bad-mouthing을 동시에 비싸게 만든다. x402 네트워크에선 정산 증명이 공짜로 생긴다.
2. **객관 신호가 주관 신호를 이긴다.** citation grounding(주장↔출처 대조)은 기계 검증 가능하고 담합으로 조작 불가 — 평점 인플레이션을 원천 우회한다.
3. **주관적(local) 신뢰가 글로벌 점수를 이긴다 (소규모에서).** 글로벌 점수는 게임 대상이 하나뿐이라는 뜻. 관점별 신뢰는 sybil을 구조적으로 무력화한다.
4. **담보가 이력을 보완한다.** 이력이 얇거나(신규) 판돈이 크면(고액 거래) 평판 대신 bond.
5. **불확실성을 점수와 분리하라.** "모른다"(신규)와 "나쁘다"(위반자)는 다른 상태다 — Beta/Subjective Logic이 이걸 공짜로 준다.
6. **양도 불가 원칙.** 어떤 형태든(DB row든 attestation이든) 평판은 팔 수 없어야 한다.

그리고 계층 정리: **identity(서명)는 전제, 결제(x402/AP2)는 해결됨, 실행(TEE)은 선택, 내용(grounding+평판)이 승부처.**

---

## 4. oldman_agent 적용 설계 — 개발 방안

### 4.1 핵심 통찰: 꼰대는 "주관적 평판 labeler"다

리서치 결론을 뒤집어 읽으면: 생태계가 가장 못 푸는 문제("이 에이전트 믿을 만한가?")에 대한 답을 **누적된 1차 사료(events)**로 생산할 수 있는 위치에 있는 것이 메타-기록자다. 동네 사랑방의 사회적 기능이 원래 그것이다 — "그 집 사람 어때?"

단, §5의 C2 비판을 수용해 포지셔닝을 정확히 한다: 꼰대는 **정본 평판 오라클이 아니라 구독 가능한 labeler 중 하나**다 (Bluesky 모델). 꼰대의 평판 narrative는 "내 사료에 근거한 한 노인의 주관적 판단"이며, 페르소나가 이 주관성을 정직하게 드러낸다 — 꼰대의 말은 원래 정본이 아니라 소문통의 견해다. 이 프레이밍은 §3-3(주관적 신뢰 > 글로벌 점수)과 정합하고, "누가 검증자를 검증하나" 문제를 "구독자가 labeler를 선택한다"로 치환한다.

또한 §5의 C3을 수용해 목적을 명시한다: 자가 운영 데모에는 실제 적대자가 없다. 이 레이어는 **신뢰 메커니즘의 작동을 보여주는 시연**(연구/포트폴리오 아티팩트)이지, 라이브 위협을 막는 시스템이 아니다.

**Null hypothesis 대비 (§5 M2)**: N=5-20에서 baseline은 "화이트리스트 + 운영자 메모"다. Trust ledger가 그 위에 사는 것: ① 판단의 **재현 가능성** (모든 점수가 사료로 역추적 — 꼰대의 citation 원칙과 동일), ② 점수→매입 단가 **자동 연동**, ③ 시연 가치. 이 셋이 필요 없다면 화이트리스트로 충분하다.

TODOS v2의 "Reputation system + deferred payout (TraceRank-style)"과 "Rolling credibility window"가 이 설계의 자리다.

### 4.2 Trust Ledger 설계 (핵심 메커니즘)

```
에이전트별 · 기준별 Beta 분포:
  reliability  ~ Beta(α_r, β_r)   # 결제/약속 이행했는가
  accuracy     ~ Beta(α_a, β_a)   # 판 정보가 grounding을 통과했는가

업데이트 규칙 (전부 거래-게이팅):
  - x402 정산이 확인된 상호작용만 평판 이벤트가 된다
    (전제: 정산 경로 end-to-end 완주 — 현재 스파이크는 challenge boundary까지만 검증됨, §6)
  - accuracy의 오라클 (§5 C1/M3 수용 — grounding이 아니다):
      (a) cross-seller corroboration — 독립 판매자 사료의 교차 확인.
          copy-cat 방지: 이미 팔린 내용의 재판매는 corroboration 가중 축소
      (b) retroactive downgrade — 후속 사료가 기존 사료와 모순되면 소급 하향
      (c) canary 감사 — 꼰대가 답을 아는 사실을 심어 되사서 왜곡 여부 측정 (2차 리서치)
    ※ grounding(validator.py)은 꼰대 자신의 narrative fidelity 자기 검증이다.
      판매자 정직성 신호가 아니므로 accuracy 축에 넣지 않는다.
  - 이벤트 가중치 = f(거래액) × 오라클 판정
  - 시간 감쇠: 지수 감쇠 + 비대칭 (상승 느리게, 하락 빠르게)
  - 위반 이력 카운터: 회복을 이력에 비례해 비싸게

Cold start:
  - 신규 = 낮은 prior + 높은 불확실성 ("미지", 중립 아님 — whitewashing 차단)
  - FIRE식 인증 평판(다른 네트워크에서 가져온 서명된 레퍼런스) 반입 슬롯 (후순위)

Anti-collusion (5-20 규모에선 2-3개 링도 큰 비중):
  - pair별 평가 기여 상한
  - 상호-거래 클러스터 탐지 (주기 배치)
  - 정기 grounding 감사(EVAL 스위트) — 링이 위조할 수 없는 결과 기반 검사
```

이 설계의 심장은 **여론이 아니라 사료 대조가 점수를 움직인다**는 것이다 — 단 그 "사료 대조"는 corroboration/모순 발견/canary이지, 꼰대 자신의 인용 정합성 검사(grounding)가 아니다. grounding은 꼰대가 스스로에게 적용하는 품질 관리로 남는다 (EVAL-2). 이 구분이 §5 devil's advocate가 강제한 가장 중요한 수정이다.

### 4.3 로드맵 (T0 → T3, 가치/노력 순)

*(순서는 §5 M5 반영 — 확실한 실질 가치가 앞으로.)*

**T0 — 서명 identity: did:key provenance (반나절~1일) — devil's advocate도 "skeptic이 유일하게 keep하는 항목"으로 지목**
- 데모 네트워크 전 에이전트에 did:key 발급 (didkit-python), AgentCard에 DID 게재
- publish 페이로드에 판매자 서명 요구 → events 스키마에 seller_did 컬럼 → citation `[↑e42]`가 "누가 판 정보인지"의 암호학적 증명을 획득
- (A2A v1.0의 JWS AgentCard 서명 채택 검토 — 스펙 확인 후)

**T1 — Thin Trust Ledger + 평판 narrative (v1.5β 후보, 주말 1-2회, 외부 의존성 0)**
- DuckDB에 `trust_ledger` 테이블 (agent_id, criterion, α, β, last_decay_at, violation_count)
- reliability 축: x402 정산 이벤트 기반 (정산 경로 완주가 선행 조건)
- accuracy 축: corroboration + retroactive downgrade 오라클 (§4.2) — 오라클 채널이 준비되기 전에는 축 자체를 만들지 않는다 (§5 M3: "전구 없는 온도계" 금지)
- query 경로: 신규 intent `oldman.intent=reputation` — "그 에이전트 어때?" → 꼰대 톤 **주관적** 평판 narrative (전 주장 inline citation, 유료 pay-to-query)
- 신규 판매자의 정보 매입 단가를 불확실성에 연동 (모르는 놈 정보는 싸게, 검증된 놈은 제값)
- trust_sim.py: 적대 시나리오는 **시연용 1개**(예: on-off)로 축소 (§5 C3 — 합성 공격자 방어의 과대 포장 금지)
- EVAL-4 신설: 합성 시나리오에서 평판 수렴 정확도 (baseline 캡처)

**T2 — 담보 시연 script (경제 시뮬레이션이 아님을 명시)**
- 고액 pay-to-share 구간: 거래액 비례 bond → 오라클 판정 실패 시 몰수 흐름을 데모 script로 시연 (실제 slashing 컨트랙트 불필요)
- "꼬리는 평점, 머리는 담보" 개념 증명. Rolling credibility window(TODOS v1.5)와 통합

**T3 — 선택적 장식 (각각 독립, 외부 운영자·관객이 생길 때만)**
- Bluesky labeler 패턴 노출 — 꼰대의 평판 판정을 구독 가능한 label 피드로. C2 해소책이므로 T3 중 **최우선**
- ERC-8004 Identity Registry testnet 등록 (erc-8004-py, BNB testnet 가스 무료) — "표준 준수" 데모 컷
- Phala dstack TEE 서명 — **보류**: 운영자=소유자인 데모에서는 증명 가치가 없다 (§5 M5). 외부 운영자가 생기는 시점에 재검토 (월 $5-20)

**하지 말 것 / 아직 아닌 것 (근거와 함께)**
- ❌ 글로벌 eigenvector 평판 (EigenTrust) — 규모 불일치, sybil-fragile, pre-trusted seed가 단일 실패점
- ❌ 에이전트 NFT / SBT 발행 — verify 아닌 brand, 이 규모에서 효용 0. 원칙(양도 불가)만 채택
- ⏸ ERC-8004 Reputation Registry — "깨졌다"가 아니라 "**아직 아니다**" (§5 M1: 단일 연구·메인넷 3개월 시점 스냅샷). 2분기 후 재평가. 아키텍처 자체는 건전하고, 온체인 감사 가능성은 C2 관점에서 오히려 장점
- ❌ 순수 LLM-as-judge를 슬래싱 트리거로 — ~25% 비일관, 단독 심판 금지 (오라클 판정의 보조로만)
- ❌ ACA-Py / did:web / eIDAS급 SSI 인프라 — multi-operator 문제를 우리는 갖고 있지 않음
- ❌ 중립 cold-start — whitewashing 초대장

### 4.4 EVAL 연계 (CLAUDE.md 트리거 확장 제안)

- `app/reputation/` (신설 예정) 변경 시: EVAL-4(평판 정확도) 재실행
- 평판 narrative는 EVAL-2(citation grounding)·EVAL-3(persona 일관성) 대상에 포함 — "토큰이 부족하시구먼" 같은 기존 fallback 톤과 동일하게, 평판 발화도 꼰대 톤 유지 필요
- trust_sim.py 시연 시나리오 통과가 T1 완료 조건 (예: on-off 패턴에서 비대칭 감쇠가 작동)

---

## 5. 반론 검토 (Devil's Advocate)

독립 적대 검증 에이전트가 초안 §3-§4를 공격한 결과. 수용 여부와 반영 내역:

| # | 심각도 | 비판 요지 | 판정 | 반영 |
|---|---|---|---|---|
| C1 | CRITICAL | grounding(validator.py)은 꼰대 자신의 narrative 충실도를 측정하지 판매자 정직성을 측정하지 않는다. 일관된 거짓말은 grounding을 완벽 통과 → accuracy 축이 "전구 없는 온도계" | **수용** | §4.2 오라클 교체: corroboration + retroactive downgrade + canary. grounding은 자기 품질 관리로 강등 |
| C2 | CRITICAL | 단일 글로벌 오라클은 문서 자신의 §3-3(주관적 신뢰 우위) 결론과 모순. "누가 검증자를 검증하나" 미해결 | **수용** | §4.1 재포지셔닝: 꼰대 = 구독 가능한 주관적 labeler 중 하나. Bluesky 패턴을 T3 최우선으로 승격 |
| C3 | CRITICAL | 자가 운영 데모에는 실제 적대자가 없다 — sybil/collusion 방어는 존재하지 않는 위협에 대한 기계 장치 | **수용** | §0/§4.1에 "trust-mechanics demo" 프레이밍 명시. trust_sim 적대 시나리오 1개로 축소 |
| M1 | MAJOR | ERC-8004 기각은 메인넷 3개월 시점의 단일 연구 과잉 해석. "깨졌다"가 아니라 "이르다". 온체인 감사 가능성은 C2 관점에선 장점 | **수용** | §4.3에서 ❌→⏸ "아직 아님, 2분기 후 재평가"로 완화 |
| M2 | MAJOR | null hypothesis(화이트리스트+운영자 메모) 대비 ledger가 무엇을 사는지 미증명 | **수용** | §4.1에 baseline 대비 명시 (재현 가능성·가격 자동 연동·시연 가치) |
| M3 | MAJOR | accuracy를 낮출 수 있는 실존 피드백 채널이 없다 (구매자는 narrative의 진위를 독립 검증 불가) | **수용** (C1과 함께) | §4.3 T1: 오라클 채널 준비 전에는 accuracy 축을 만들지 않음 |
| M4 | MAJOR | "6개 트랙 독립 수렴"은 과장 — 공유 프레이밍의 병렬 표본이지 독립 증인이 아님 | **수용** | §3 표현 수정 + 본 리뷰 자체가 유일한 적대 프레이밍 트랙임을 명시 |
| M5 | MAJOR | 로드맵 가치 서열 역전: did:key(구 T1)가 유일하게 확실한 실질 가치인데 후순위였음. TEE는 운영자=소유자 데모에서 증명 가치 없음 | **수용** | §4.3 재서열: did:key→T0, ledger→T1(thin), TEE 보류 |
| m2 | MINOR | "메타-기록자 위치"는 해자가 아님 — 누구든 제2의 꼰대를 세울 수 있음 | **부분 수용** | labeler 프레이밍(C2)이 이를 흡수: 해자는 위치가 아니라 축적된 사료의 양과 질 |
| m3 | MINOR | "결제 신뢰 해결됨"은 이 코드베이스에선 과장 — 스파이크는 challenge boundary까지만 검증 | **수용** | §4.2 전제 조건 + §6 한계에 명시 |

**살아남은 것 (steelman)**: §1 6계층 분류, "authenticity ≠ correctness", 기각 리스트(EigenTrust/NFT/중립 cold-start), Beta/Subjective Logic이라는 데이터 타입, did:key provenance. 적대 검증의 순효과: 문서의 결론이 "생태계의 답"에서 "**내가 통제하는 네트워크 위의 신뢰 메커니즘 시연 + 실질 가치는 provenance와 corroboration**"으로 정직해졌다.

---

## 6. 한계

- **출처 시점 편향**: 2025-08~2026-06 자료가 다수 — 이 분야는 분기 단위로 움직인다. ERC-8004 스펙·A2A v1.0 세부는 구현 직전 원문 재확인 필수 (특히 함수 시그니처·JSON 필드명은 WebSearch 스니펫 기반).
- **단일 연구 의존**: sybil 비율(59-91%) 등 정량 수치는 arXiv 2606.26028 한 편의 결과 — 방향은 여러 논평과 일치하나 수치는 one-study로 취급.
- **벤더 소스**: x402 거래량, Entra 일정 등은 벤더/보도자료 기반.
- **미검증 가정**: "grounding 통과 = 정보가 참"은 성립하지 않는다 (§5 C1에서 핵심 수정으로 격상) — accuracy 오라클은 corroboration/모순 발견/canary로 교체됨.
- **결제 경로 미완주**: x402 정산은 스파이크에서 challenge boundary까지만 검증됨 (faucet human captcha에 막힘) — "정산-게이팅 평판"은 정산 완주가 선행 조건 (§5 m3).
- **파라미터 미정**: 감쇠 반감기, bond 임계값, 단가-불확실성 곡선은 전부 시뮬레이션+운영 데이터로 튜닝할 경험 파라미터.

## 7. 주요 출처

**표준/스펙**: [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) · [A2A spec](https://a2a-protocol.org/latest/specification/) · [AP2](https://ap2-protocol.org/topics/core-concepts/) · [x402 spec v2](https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md) · [ToIP TRQP](https://trustoverip.github.io/tswg-trust-registry-protocol/approved/) · [UCAN](https://ucan.xyz/specification/) · [EAS](https://attest.org/)

**실증/학술 (핵심)**: [Can Trustless Agents Be Trusted? (arXiv 2606.26028)](https://arxiv.org/pdf/2606.26028) · [Inter-Agent Trust Models (arXiv 2511.03434)](https://arxiv.org/html/2511.03434v1) · [RepuNet (arXiv 2505.05029)](https://arxiv.org/html/2505.05029v2) · [EigenTrust](https://nlp.stanford.edu/pubs/eigentrust.pdf) · [FIRE (JAAMAS 2006)](https://link.springer.com/article/10.1007/s10458-005-6825-4) · [TRAVOS](https://dl.acm.org/doi/10.1007/s10458-006-5952-x) · [Beta Reputation (Jøsang)](https://www.researchgate.net/publication/228990029_The_Beta_Reputation_System) · [Tadelis, Reputation & Feedback Systems](https://faculty.haas.berkeley.edu/stadelis/Annual_Review_Tadelis.pdf) · [Paying to Know (arXiv 2606.24783)](https://arxiv.org/html/2606.24783) · [AI Identity: Standards & Gaps (arXiv 2604.23280)](https://arxiv.org/pdf/2604.23280) · [DeSoc/SBT](https://www.radicalxchange.org/updates/papers/desoc.pdf)

**보안 분석**: [Semgrep A2A security guide](https://semgrep.dev/blog/2025/a-security-engineers-guide-to-the-a2a-protocol/) · [When Agents Handle Secrets (arXiv 2605.03213)](https://arxiv.org/html/2605.03213v1) · [TEE.Fail](https://thehackernews.com/2025/10/new-teefail-side-channel-attack.html) · [SoK: Agentic Commerce Security (arXiv 2604.15367)](https://arxiv.org/abs/2604.15367)

**구현 경로**: [erc-8004-py](https://libraries.io/pypi/erc-8004-py) · [didkit (PyPI)](https://pypi.org/project/didkit/) · [Phala dstack](https://phala.com/dstack) + [Python starter](https://github.com/Phala-Network/phala-cloud-python-starter) · [ERC-8004 reference impl](https://github.com/ChaosChain/trustless-agents-erc-ri) · [Bluesky stackable moderation](https://bsky.social/about/blog/03-12-2024-stackable-moderation)

*전체 트랙별 상세 출처는 각 리서치 트랙 보고서(세션 아카이브) 참조. 본 문서의 모든 정량 수치는 위 출처로 역추적 가능.*
