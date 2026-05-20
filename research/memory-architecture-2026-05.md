# Memory Architecture Deep Research — 2026-05-19

Synthesizing FA1 (structure) + FA2 (cost economics) + FA3 (selection/triage) sub-agent reports.
Project: oldman_agent v1. Scale: 5~20 agents, dozens~hundreds events/day. Side project, 5 weekend cap.

---

## TL;DR (한 줄 결론)

> **현재 4-layer는 방향은 맞지만 L1/L3가 under-specified.** 가장 큰 누수는 (1) L0 게이트 부재 — 모든 event가 reflection까지 흘러감, (2) L3가 "JSON 캐시"로만 정의되어 sleep-time compute 잠재력 미활용, (3) self-publish 신뢰 모델 없음. 셋 다 1~2 주말 안 minor patch로 해결 가능.

근거: Mem0 production 데이터 90% 토큰 절감, ENGRAM 15pt 정확도 lift, D-MEM/True-Memory 게이트 AUC 0.73→0.82, Letta sleep-time 5× test-time 절감, EMNLP 2025 multi-observer self-report bias 확증.

---

## 우리 4-layer의 약점 (직접 비교 분석)

| Layer | 현 설계 | 2025-2026 baseline | Gap |
|---|---|---|---|
| **L0 events** | append-only, dedup만 | D-MEM/True-Memory가 권장: 게이트 통과한 event만 저장 (Transient drop, 40~60% pre-filter) | **모든 event를 무조건 저장**. spam/noise 흡수 비용 큼 |
| **L1 entities** | semantic+episodic 혼재 한 테이블 | ENGRAM: typed 분리 시 LongMemEval +15pt; 자료원 출처 메타 (source_type) 없음 | Provenance 부재 → self-report 미화/spam 미구분 |
| **L2 reflections** | scope=agent/pair/society, min(10ev,6h) | Letta sleep-time agent 권장 N≥5 (만족), Zep graph는 600K tok/conv 폭증 → 우리 규모엔 과함 | society-scope는 graph 잠재력 있지만 별도 DB는 과투자. **L3에 흡수가 더 경제적** |
| **L3 materialized_traits** | "JSON 캐시" — 스키마 미정 | Mem0 production: cache-first read path가 90% 토큰 절감 가져옴. 사전 계산된 narrative 답변까지 캐싱 권장 (sleep-time compute) | **highest ROI 인데 가장 vague**. precomputed query JSON 스키마 설계 필요 |

---

## 핵심 인용 (numbers only, 추측 제거)

**구조 (FA1)**
- Mem0 cache-first vs Zep graph: 49% vs 63.8% LongMemEval, 그러나 Zep은 600K tok/conv (85× 많음). 데모 규모엔 Mem0 패턴 ROI 압승. ([AgentMarketCap, 2026-04](https://agentmarketcap.ai/blog/2026/04/11/agent-memory-architecture-production-2026))
- GraphRAG: single-hop −13.4%, multi-hop +54pt. 우리 society scope만 multi-hop. ([arXiv 2502.11371](https://arxiv.org/abs/2502.11371v1))
- ENGRAM: episodic/semantic 분리 + dense retrieval = +15pt LongMemEval, 토큰 ~1%로. ([OpenReview 2025](https://openreview.net/pdf?id=D7WqEZzwRR))
- Letta sleep-time: 5× test-time 토큰 절감, 10 관련 query 분산 시 query당 −2.5×. ([arXiv 2504.13171](https://arxiv.org/abs/2504.13171))

**경제성 (FA2)**
- Haiku+1reflection > Sonnet+0reflection on structured tasks, prompt caching = −28% on top. ([arXiv 2510.20653](https://arxiv.org/abs/2510.20653))
- Batch API: −50% pricing. Nightly consolidation $1.17/night for 13-cron agent. ([sleep-consolidation note](https://github.com/globalcaos/tinkerclaw/blob/main/docs/papers/sleep-consolidation/sleep-consolidation.md))
- LLMLingua-2: 3.7× 압축, latency −18%, summarization/QA quality 보존, few-shot/code 성능 저하. ([arXiv 2403.12968](https://arxiv.org/abs/2403.12968))
- RECOMP extractive: 94% token 절감, 무관 context는 empty string 출력 (selective augmentation). ([ICLR 2024](https://arxiv.org/html/2310.04408v1))
- Mem0 write-time ADD/UPDATE/DELETE/NOOP dedup: +26% accuracy vs OpenAI memory on LOCOMO.

**Triage (FA3)**
- True-Memory 3-signal gate (novelty + salience + prediction-error): AUC 0.816 vs PE-only 0.730. PE는 novelty와 r=0.30 으로 독립 시그널. ([arXiv 2605.04897](https://arxiv.org/html/2605.04897v1))
- D-MEM RPE = Surprise × Utility-tier, hard τ gate로 noise drop. ([arXiv 2603.14597](https://arxiv.org/pdf/2603.14597))
- EMNLP 2025 multi-observer: self-report는 systematic over-positive bias, 5-7 observer consensus가 human alignment 회복. ([ACL 2025](https://www.aclanthology.org/2025.findings-emnlp.1150/))
- A-Trust: 20-event rolling violation window, 100% ADR. ([arXiv 2506.02546](https://arxiv.org/pdf/2506.02546))
- TraceRank Sybil 저항: 0-reputation 시드들의 payment는 reputation 0. ([arXiv 2510.27554](https://arxiv.org/html/2510.27554v1))

---

## "뭘 메모리에 넣을까" — 결정 알고리즘 제안

이게 사용자가 핵심으로 물어본 부분. 위 인용 기반으로 단일 algorithm 으로 합성:

```
on incoming event e from agent A:
  # 0. Cheap rule gate (no LLM)
  if e.kind in BLOCKLIST {heartbeat, ack, status_dup}: DROP
  if jaccard(e.payload, last_5_events(A)) > 0.9: DROP

  # 1. Embed + nearest-neighbor lookup against L1
  emb_e = embed(e)
  nn = nearest_neighbor(emb_e, L1_index)
  novelty = 1 - cosine(emb_e, nn.emb)              # True-Memory signal 1
  prediction_error = embedding_xpair_divergence(   # True-Memory signal 3
                       cross=(e, nn),
                       self=(nn, nn))

  # 2. Haiku triage call (2-field structured JSON)
  triage = haiku_call({
    surprise: novelty,
    pe: prediction_error,
    schema: {tier: enum(transient|episodic|persistent),
             utility: 0..1}
  })

  if triage.tier == "transient": DROP            # 40~60% expected drop here
  if triage.tier == "episodic" : insert L0 only
  if triage.tier == "persistent":
      # 3. Source provenance + trust weighting
      src_weight = SELF=0.7 | THIRD_PARTY=1.0 | MUTUAL=1.2
      credibility = src_weight * A.credibility_score   # rolling 20-event window
      effective_score = (0.5*novelty + 0.3*pe + 0.2*triage.utility) * credibility

      insert L0
      if effective_score > τ_high:
        upsert L1 (entity update with provenance: (A, e.id, src_type, ts))
        flag for L2 reflection batch

      # Contradiction routing (PE > 0.5 = belief revision)
      if prediction_error > 0.5:
        L1.entity.flags |= CONTRADICTION
        immediate L2 targeted reflection (not full evolution)

# 4. Nightly batch (Batch API discount −50%)
nightly:
  for agent in active_agents:
    if agent.pending_events >= 10 or 6h elapsed:
      ctx = LLMLingua-2 compress(L1[agent].recent + L2[agent].recent, ratio=3.7x)
      reflection = haiku(prompt=ctx, cache=system_prompt)
      L2 insert(reflection)
      # 5. Sleep-time precompute (Letta pattern)
      for q in TOP_3_PREDICTED_QUERIES(agent):  # "trait?", "recent activity?", "relations?"
        ans = opus(reflection)
        L3.precomputed[agent][q] = ans

# 6. Query path: cache-first
on query(agent):
  if L3.precomputed[agent][q] exists and fresh: return immediately  # Mem0 90% savings
  else: opus(retrieve L2 + L1, with RECOMP selective augmentation)
```

핵심 변화점:
1. **L0가 게이트를 통과한 event만 받음** (현재는 무조건 저장).
2. **importance scoring을 LLM 1-10 → embedding-only signals**로 (Haiku 호출 1번만, 그것도 structured JSON).
3. **L1에 provenance 메타 4개 추가** (source_type, source_agent, corroboration_count, credibility).
4. **L3가 사전 계산된 narrative 답변 저장소**로 격상 (단순 traits 캐시 → query cache).

---

## 권장 아키텍처 수정안 — 3 옵션

### Option A — Minor Patch (추가 1 주말, ROI 高)

**유지**: 4-layer 토폴로지, DuckDB, A2A surface, 꼰대 페르소나.

**추가**:
1. L0 앞에 **2단계 게이트** — rule-based blocklist + Jaccard dedup (LLM 미사용).
2. L1에 4개 컬럼 추가: `source_type ENUM(self|third_party|mutual)`, `source_agent`, `corroboration_count INT`, `credibility_score FLOAT`.
3. Reflection 호출 시 **prompt caching 켜기** (Anthropic SDK 1줄).
4. L3 스키마 명시화: `materialized_traits.precomputed_queries: {"trait?": "...", "recent?": "...", "relations?": "..."}` 사전 계산 3개.

**비용 영향 (estimated)**: −50~65% reflection token spend, −40% L0 storage, narrative 답변 query 평균 latency −60%.
**리스크**: 적음. v1 milestone 안에 들어감.

---

### Option B — Major Rewrite (추가 2~3 주말, ROI 高, 추천)

Option A + 다음:

5. **L0를 게이트된 store로 변경** — 위 "결정 알고리즘"의 2-axis RPE Haiku triage 호출 도입. 40~60% pre-filter.
6. **L1 typed split** — `entities_semantic` (stable traits, upsert) + `entities_episodic` (events with provenance, append). ENGRAM 15pt 근거.
7. **Reflection batching** — per-event inline → **nightly Batch API job**. −50% pricing + LLMLingua-2 입력 압축 3.7×.
8. **prediction-error signal 추가** — embedding cross-pair divergence, 추가 모델 호출 0회. AUC 0.73→0.82 lift.
9. **L3에 sleep-time precomputed Q&A 본격 도입** — reflection 끝나는 시점에 Top-3 예측 query에 대해 Opus 1회 호출, 답 캐싱. Mem0 90% 토큰 절감 패턴 정착.

**비용 영향**: Option A 위에 추가로 narrative path Opus spend −70%, reflection pipeline 전체 −80% (Batch + 압축 + pre-filter 곱).
**리스크**: nightly job 도입으로 freshness lag (수 시간). 5-20 agent demo에서 수용 가능.
**검증 evidence**: Mem0/Letta/ENGRAM 모두 production 데이터 있음.

---

### Option C — Radical Alternative (추가 4~5 주말, ROI 중간, deferral 권장)

**버림**: 4-layer 토폴로지. 2-layer로 단순화.

**변경**:
- L0(events) + L_mem(memories)만. L_mem이 L1+L2+L3 통합 (Mem0 패턴 그대로).
- 모든 write가 ADD/UPDATE/DELETE/NOOP classifier 거침 (Mem0 production 패턴, LOCOMO +26% accuracy).
- Society-scope만 **별도 edge table** (lightweight graph) — multi-hop reasoning 케이스만. Zep Graphiti 패턴 축소판.
- 꼰대 페르소나 prompt에 retrieval result를 RECOMP-compress + selective-augment 만 적용.

**왜 추천 안 함**: 
- Mem0 패턴은 conversational memory에 최적화 — A2A inter-agent observation 시그널이 약화될 위험 (3자 관찰의 가중치를 별도 column 으로 표현하기 어려움).
- 5-weekend cap 안에 마이그레이션 + 검증 어려움.
- ROI 가 Option B 대비 한계 효용 적음 (Option B가 이미 90% 절감 도달).

**언제 고려**: v2에서 50+ agents 스케일링 필요할 때 재검토.

---

## 최종 권고

**Option B를 v1 PRD에 반영. Option A는 fallback (시간 부족 시).**

PRD 변경 사항 (이 권고가 채택되면):
- `Open Questions`에 묶여 있던 "Vector index 도입 여부" → **Option B로 해결됨** (embedding-based signals만 활용, vector index 불필요).
- `Risks` 표에 "self-publish bias / spam" 행 추가 → mitigation: source_type discount + credibility_score (Option B 항목 8).
- Milestone 2 ("Memory pipeline alive")를 다음으로 분해:
  - 2a. L0 게이트 (rule + RPE/PE/utility Haiku triage)
  - 2b. L1 typed split + provenance
  - 2c. Reflection nightly batch + prompt caching + LLMLingua-2
  - 2d. L3 sleep-time precomputed Q&A
- `Success Metrics` 표에 추가: "Pre-filter drop rate" target 40~60%, "L3 cache hit rate on query" target ≥70%.

v1.5 (결제 통합)에 자연스럽게 연결되는 부분:
- v1.5 spam economics → 이미 credibility_score / source_type infra가 있으므로 TraceRank-style reputation 외삽 쉬움.
- 결제 받은 publisher의 신뢰도는 별도 column `paid_publisher_tier`로만 추가.

---

## Sources (consolidated)

- [arXiv 2502.11371 — RAG vs GraphRAG systematic eval](https://arxiv.org/abs/2502.11371v1)
- [arXiv 2504.13171 — Sleep-time Compute (Letta/Berkeley)](https://arxiv.org/abs/2504.13171)
- [arXiv 2510.20653 — Reflection sweet spot (Amazon Science)](https://arxiv.org/abs/2510.20653)
- [arXiv 2403.12968 — LLMLingua-2](https://arxiv.org/abs/2403.12968)
- [arXiv 2310.04408 — RECOMP](https://arxiv.org/html/2310.04408v1)
- [arXiv 2603.14597 — D-MEM dopamine gate](https://arxiv.org/pdf/2603.14597)
- [arXiv 2605.04897 — True Memory three-signal gate](https://arxiv.org/html/2605.04897v1)
- [arXiv 2506.02546 — A-Trust](https://arxiv.org/pdf/2506.02546)
- [arXiv 2510.27554 — TraceRank Sybil resistance](https://arxiv.org/html/2510.27554v1)
- [arXiv 2510.18563 — Trust-Vulnerability Paradox](https://www.arxiv.org/abs/2510.18563)
- [OpenReview ENGRAM 2025](https://openreview.net/pdf?id=D7WqEZzwRR)
- [ACL 2025 — Multi-Observer Agents](https://www.aclanthology.org/2025.findings-emnlp.1150/)
- [AgentMarketCap memory architecture 2026-04](https://agentmarketcap.ai/blog/2026/04/11/agent-memory-architecture-production-2026)
- [Letta sleep-time docs](https://docs.letta.com/guides/agents/architectures/sleeptime/)
- [Mem0 vs Zep vs Letta — HydraDB](https://hydradb.com/blog/mem0-vs-zep-vs-letta)
