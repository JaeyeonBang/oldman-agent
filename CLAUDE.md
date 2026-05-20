# oldman_agent — 동네 사랑방

A2A 에이전트 생태계의 메타-기록자. 다른 에이전트들의 정보·일화를 수집·축적·구조화하고, 꼰대 페르소나로 사회 history narrative를 제공한다. **양방향 결제 토폴로지** (ap2/x402): pay-to-share + pay-to-query.

**Status**: pre-code, design doc complete (`/office-hours` + `/plan-eng-review` 완료 2026-05-19).
**Mode**: Builder (사이드 프로젝트, 사용자 직접 운영하는 5-20 에이전트 데모 네트워크)

---

## Project Context

- **Stack**: Python (추정) + A2A SDK + ap2 + x402 + DuckDB (event store) + LLM (Haiku default, Opus for storytelling tier)
- **Persona**: 꼰대 정보통 (1인칭 노년 화자, **inline citation 강제** — 모든 주장은 `[↑e42]` / `[↑r07]` ref 필수)
- **Differentiator**: 양방향 결제. 꼰대가 정보를 사들이고(pay-to-share), narrative로 되판다(pay-to-query)

## Where to find context

| File | Purpose |
|---|---|
| `~/.gstack/projects/oldman_agent/qkdwodus777-unknown-design-20260518-231759.md` | 메인 설계 문서 (D1-D7 결정 + GSTACK REVIEW REPORT + Implementation Tasks) |
| `~/.gstack/projects/oldman_agent/qkdwodus777-unknown-eng-review-test-plan-20260519-000837.md` | Test plan artifact (EVAL suites, critical paths, edge cases) |
| `~/.gstack/projects/oldman_agent/tasks-eng-review-20260519-002753.jsonl` | 9 implementation tasks (T1-T9, P1×5/P2×3/P3×1) |
| `./TODOS.md` | Task tracking with pivot triggers + open questions |
| `./memory.md` (49KB) | 학술 리서치: Multi-Agent System 종합 조사 (Generative Agents, MemGPT, A-MEM, SDT, Reactance 등 70+ 사례) |
| `./memory2.md` (28KB) | 학술 리서치: "사회적 틀의 의인화" 선행 프로젝트 매핑 |

memory.md / memory2.md는 persona 작성·reflection 알고리즘 설계 시 참조 자료. 코드 reuse 없음.

## Build / Test / Lint (placeholder — Python 추정)

코드 진입 전이라 명령은 placeholder. T8 mock layer 또는 첫 spike 작성 시 교체.

```bash
# Install
pip install -r requirements.txt

# Test
pytest                    # unit
pytest tests/e2e/         # e2e (publish→query 사이클)
python scripts/eval.py    # LLM eval suites (EVAL-1/2/3)

# Lint / type check
ruff check .
mypy app/
```

## Prompt / LLM changes

다음 파일 변경 시 `/plan-eng-review` EVAL 트리거 — 변경 사항 review에서 EVAL 재실행 명시 필요:

- `app/narrative/renderer.py` — 꼰대 페르소나 system prompt + inline citation 강제 instruction
- `app/narrative/validator.py` — citation source 검증 로직 (hallucination 차단)
- `app/reflection/scheduler.py` — reflection 생성 LLM 호출
- `config/llm.yaml` — model tier routing (Haiku/Sonnet/Opus) + token budget per reflection / per query
- 모든 `prompts/*.md` 파일

연관 EVAL:
- **EVAL-1**: Reflection accuracy — golden set 5-10 cases, 동일 event set → 생성된 reflection이 actual content 반영
- **EVAL-2**: Citation grounding — 100 narrative response에서 hallucinated claim 비율 (목표: 0%, fail threshold 1%)
- **EVAL-3**: Persona consistency — 꼰대 톤 일관성 (subjective rubric 또는 model-judge)

Baseline은 v1 ship 시점 fixed set으로 캡처.

## Pivot Trigger

> Spike A (T1: outbound x402) 또는 Spike B (T2: inbound ap2)가 1일 이상 막히면 → **"Design note + simulated demo"** 피벗.
> 데모 영상의 모든 결제·SDK 호출을 cinematic mock으로. 80% 가치를 20% 비용에.

---

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

### gstack 스킬
- Product ideas/brainstorming → invoke `/office-hours`
- Strategy/scope challenge → invoke `/plan-ceo-review`
- Architecture / test plan review → invoke `/plan-eng-review`
- Design system/plan review → invoke `/design-consultation` or `/plan-design-review`
- Full review pipeline (CEO+Eng+Design+DX) → invoke `/autoplan`
- Bugs/errors/"why is this broken" → invoke `/investigate`
- QA/testing live site behavior → invoke `/qa` or `/qa-only`
- Code review / diff check / pre-landing → invoke `/review`
- Visual polish on live site → invoke `/design-review`
- Ship/deploy/push/create PR → invoke `/ship` or `/land-and-deploy`
- Save context for later → invoke `/context-save`
- Resume saved context → invoke `/context-restore`
- Codex independent 2nd opinion → invoke `/codex`

### ecc 플러그인 (대안 / 보조)
- 전체 ecc 카탈로그 안내 → `/ecc:ecc-guide`
- Python 코드 리뷰 → `/ecc:python-review`
- TDD 워크플로우 (Python/Django/FastAPI) → `/ecc:tdd-workflow`
- 보안 스캔 → `/ecc:security-scan`
- 프로덕션 감사 → `/ecc:production-audit`
- 세션 저장/복원 → `/ecc:save-session` / `/ecc:resume-session`
- 학습/메모리 → `/ecc:learn`

### 호출 순서 규칙
1. 코드 작성 직전 → `/plan` (간단) 또는 `/plan-eng-review` (architecture 영향 시)
2. 코드 작성 직후 → `/review` (diff 기반) 또는 `/ecc:python-review` (언어 특화)
3. ship 직전 → `/ship` (gstack workflow)
4. 세션 종료 전 → `/context-save` (다음 세션에서 `/context-restore`로 복원)

## Conventions

- **Python style**: PEP 8 + ruff. Type hints 필수 (mypy strict 권장 v1.5에서).
- **Immutability**: 데이터 흐름은 dataclass(frozen=True) 또는 pydantic. mutation 회피.
- **Validation at boundaries**: API 입력은 pydantic schema, internal은 trust internal code (`/rules/golden-principles.md` 준수).
- **Tests first**: TDD (Red → Green → Improve). 80%+ coverage 목표.
- **Surgical changes**: 1 commit = 1 logical change. 인접 코드 정리 별도 commit.
- **Korean for docs/comments, English for code identifiers**: persona / narrative / domain 용어는 한글, 변수/함수는 영문.

## Open Questions (pending evidence)

- A2A SDK pub/sub 패턴 존재 여부 → Spike A2A SDK quickstart에서 결정
- pay-to-share / pay-to-query 단가 비율 → v1 ship 후 메트릭 기반 조정
- 자율성 욕구 agent 인터페이스 약속 → v2 진입점에서 결정
