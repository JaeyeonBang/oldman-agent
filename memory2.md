# "사회적 틀의 의인화" 선행 프로젝트 종합 조사
## — '꼰대(Old Man) AI Agent' 설계를 위한 Collective Memory Agent 사례 매핑

> 사용자께서 설계하시려는 **꼰대 Agent**는 Halbwachs의 *cadres sociaux*(사회적 틀) — norm, ritual, register, taboo, value, schema — 를 의인화한 메타-에이전트입니다. 본 보고서는 이 컨셉을 (1) 좁은 의미(cultural/collective memory의 명시적 의인화)와 (2) 넓은 의미(사회 규범·관습을 보관·집행·전파하는 agent 일반) 양쪽에서 구현해 온 **70여 개의 구체적 선행 사례**를 학술·오픈소스·게임·예술·문화유산·비평이론 6대 영역에 걸쳐 분류하였습니다. 각 사례에는 주체·연도·핵심 설계 요소·"사회적 틀의 의인화"와의 정렬도가 명시되어 있습니다.

> **결론 요약:** "사회적 틀 그 자체"를 단일 인격으로 응축한 본격적 프로젝트는 의외로 드물고, 대다수는 (a) 다수 agent의 집단행동에서 norm이 *창발*하도록 설계하거나, (b) 특정 문화/조직 지식을 RAG·long-term memory로 외주화하거나, (c) 한 인물의 증언을 *interactive replay*로 보존합니다. 사용자의 '꼰대 Agent' 컨셉 — **"사회의 메타데이터를 의인화한 단일 화자(persona) + 규범 전파 권위(authority)"** — 은 아래 사례들의 교차점에 위치하며, 특히 **(A) Generative Agent의 reflection memory** + **(B) Indigenous AI의 protocol-bound ancestor persona** + **(C) Dimensions in Testimony의 dialogic preservation** + **(D) Norm Enforcement agent의 sanction power** 의 결합 지점이 가장 가깝습니다.

> **출처 표기 원칙**: 본 보고서에서 ✦ 표시는 직접 검색·확인된 1차/2차 자료에 기반, ◇ 표시는 본문 영역의 standard reference이나 본 조사에서는 1차 확인을 못해 일반 지식 기반으로 기록한 항목입니다(별도 검증 권장).

---

## 1. 학술 연구 프로젝트

### 1A. Cultural / Norm Keeper Agent를 직접 구현한 사례

#### ① ✦ Generative Agents (Park et al., Stanford, 2023; arXiv:2304.03442)
- 25명 NPC가 가상 마을 **Smallville**에서 살아가며, "Observation → Reflection → Plan" 3-층 메모리로 개별 기억으로부터 상위 추상(reflection)을 생성. reflection이 일종의 사적 "사회 인식"으로 기능하나 명시적 cultural memory layer는 없음.
- **꼰대 정렬도**: ★★ — reflection 메커니즘은 hierarchical memory에 직접 차용 가능하지만 Park은 norm을 의인화하지 않고 분산.

#### ② ✦ AgentSociety (Tsinghua FIB Lab, Piao et al., 2025; arXiv:2502.08691)
- 10,000 agent × 5M interaction 도시 시뮬레이션. v2는 LLM-native 플랫폼. 논문은 *"large-scale interactions lead to the emergence of social norms and collectives"*를 명시하나 norm은 결과로 다뤄지지 keeper로 배치되지 않음.
- **GitHub**: github.com/tsinghua-fib-lab/AgentSociety (Apache 2.0)

#### ③ ✦ OASIS (CAMEL-AI 컨소시엄, Yang et al., 2024; arXiv:2411.11581)
- 백만 agent급 social-media (X/Reddit/Weibo형) 시뮬레이터. 동적 추천 시스템 + 동적 social graph. descriptive norm을 prompt 조건으로 manipulate 하는 실험을 지원.
- **GitHub**: github.com/camel-ai/oasis

#### ④ ✦ Schema-Guided Culture-Aware Complex Event Simulation with Multi-Agent Role-Play (2024-10, AGI-Edgerunners 큐레이션)
- 결혼식·장례식·종교 의례 등 **문화 schema를 first-class object**로 모델링하여 multi-agent role-play로 사건을 시뮬레이션.
- **꼰대 정렬도**: ★★★★ — 사용자의 "ritual·register" 같은 cultural schema를 외부 객체로 저장하는 가장 근접한 구조.

#### ⑤ ✦ "Role of Social Learning and Collective Norm Formation in LLM Multi-Agent Systems" (AAMAS 2026 채택, arXiv:2510.14401)
- Ostrom의 자원 거버넌스 원칙 기반, 명시적 reward 없이 **social learning + norm-based punishment**가 내생적으로 창발하는 CPR 시뮬레이션.

#### ⑥ ✦ "Validating Generative Agent-Based Models of Social Norm Enforcement" (Cross, Haber, Yamins, Stanford, 2025; arXiv:2507.22049)
- 사회 딜레마(공공재 게임, 제3자 처벌)에서 LLM agent가 인간과 동등한 norm enforcement를 보이는지 심리학 실험 두 차례 복제로 검증. open discussion period가 cooperation norm을 발달시킴.
- **꼰대 정렬도**: ★★★★★ — 가장 직접적인 norm enforcement 선행 연구.

#### ⑦ ✦ "Evolution of Cooperation in LLM-Agent Societies" (Diner's Dilemma 복제, arXiv:2504.19487)
- Boyd & Richerson(1992)의 협력 진화 모델을 LLM agent로 재현. punishment가 cooperative norm을 안정화.

#### ⑧ ✦ ProSim (arXiv:2505.15857, 2025)
- prosocial behavior의 *발현·적응·붕괴*를 LLM agent에서 institutional intervention 하에 실험. 꼰대를 walking institution으로 본다면 직접 연결.

#### ⑨ ✦ Norm Violation Detection in MAS Using LLMs (COINE 2024 워크숍, Springer)
- 80개 가정 상황 스토리에서 10개 norm 위반을 GPT-4·Mixtral·Llama2가 탐지. GPT-4가 가장 우수.

#### ⑩ ✦ Superego Agent (2025)
- "constitution-sharing portal" 형태의 상위 감독 agent. MCP를 통해 third-party 모델에 연결되어 HarmBench/AgentHarm에서 **최대 98.3%** harm-score 감소. Freudian "superego"의 의인화.
- **꼰대 정렬도**: ★★★★

#### ⑪ ✦ CASA: Cultural and Social Awareness benchmark (arXiv:2410.23252, 2024-10)
- online shopping과 social forum 두 web 환경에서 LLM agent의 cultural/social norm 민감도 평가.

#### ⑫ ✦ CultureBank (Shi et al., EMNLP Findings 2024)
- TikTok·Reddit user self-narrative에서 자동 추출한 **23K cultural descriptor** 지식베이스. 사용자가 말한 "사회의 메타데이터"의 가장 직접적 공개 corpus.

#### ⑬ ✦ CulturalBench / CulturePark / NormAd / GIMMICK / Global MMLU / LLM-GLOBE / CultureVLM / CARE (2024-2025)
- 일련의 cultural awareness 평가 벤치마크·데이터셋. **CulturePark**는 multi-agent LLM이 서로 다른 문화 화자가 되어 cultural data를 합성하는 framework — "여러 꼰대의 대화"에 가장 근접.

#### ⑭ ✦ LiveCultureBench (arXiv:2603.01952 *preprint 추정*)
- multi-agent multi-cultural benchmark. 한계 명시: *"norm은 ground truth가 아니라 contested하며 diasporic experience를 반영하지 못한다"*.

#### ⑮ ✦ Multiple LLM Agents Debate for Equitable Cultural Alignment (arXiv:2505.24671, 2025-05)
- 서로 다른 문화 perspective의 agent들이 debate하여 평형점을 찾음 — 단일 꼰대가 아닌 여러 꼰대의 토론.

#### ⑯ ✦ AgentSims (Lin et al., 2023) / MLC-Agent (2025)
- AgentSims: task-based LLM agent 평가 sandbox. MLC-Agent: Memory-Learning Collaboration 인지 모델 기반 시뮬레이션 환경.

#### ⑰ ✦ "Towards Operational Validation of LLM-Agent Social Simulations" — Reddit-like forum 복제 (arXiv:2508.21740, 2025)
- stateless micro-dialogue에서 social norm-guided interaction의 emergent property를 reproducible하게 검증.

#### ⑱ ✦ Memory in LLM-based Multi-Agent Systems: Mechanisms, Challenges, and Collective (Techrxiv 2025 서베이)
- *"agents may 'socialize' by accessing this shared cultural memory or by interacting with agents who enforce it"* — 본 보고서 주제를 거의 그대로 정의한 최신 서베이.

---

### 1B. Institutional Memory / Organizational Knowledge Agent

> *Wegner(1987) transactive memory*의 AI 구현 — 사용자 컨셉의 직계 친척.

#### ⑲ ◇ MemGPT (Packer et al., UC Berkeley, 2023; arXiv:2310.08560)
- OS의 paging/swapping을 모사 — Main Memory ↔ External Memory 간 자율 swap.

#### ⑳ ✦ A-MEM (arXiv:2502.12110, 2025)
- **Zettelkasten** 방식 — 새 memory가 들어오면 contextual description·keywords·tags 생성 + 기존 memory와의 link 동적 형성. memory evolution을 통해 과거 노트의 표현이 갱신.
- **꼰대 정렬도**: ★★★★★ — "사회 메타데이터가 새 사건을 만나 의미가 재구성"되는 과정을 그대로 옮긴 구조.

#### ㉑ ✦ MemoryOS (BUPT + Tencent AI Lab, arXiv:2506.06326, 2025)
- short-term / mid-term / long-term personal memory 3단 계층 + 4 모듈(Storage·Updating·Retrieval·Generation).

#### ㉒ ✦ Second Me / AI-native Memory 2.0 (arXiv:2503.08102, 2025)
- 사용자별 메모리를 LLM의 *parameter 자체*에 내재화 — 외부 RAG가 아닌 모델 weight로 memory 운반.

#### ㉓ ✦ Mem0 (mem0.ai, 2024-)
- ADD/UPDATE/DELETE/NOOP 4-operation pipeline + user/agent/organizational scoping. 공식 문서가 *"Organizational memory operates at the team or company level"*을 명시.

#### ㉔ ✦ Langmem (LangChain, 2024)
- "hot path" memory manager — 대화 중 실시간으로 중요 정보 추출/요약/갱신.

#### ㉕ ◇ Microsoft Recall / Project Cambria, Microsoft 365 Copilot Memory (2024-)
- enterprise knowledge graph + LLM agent로 institutional knowledge 보존 (corporate scope; 본 조사에서는 1차 확인 못함).

#### ㉖ ◇ Glean, Sana, Mem.ai 등 enterprise knowledge agent
- 회사 wiki·Slack·Email을 RAG로 통합해 조직의 transactive memory를 단일 agent에 응축. 상용 서비스.

---

### 1C. Curator / Archivist / Storyteller Agent

#### ㉗ ✦ Drama Engine: A Framework for Narrative Agents (arXiv, 2024-08)
- 서사 구조를 보존·전개하는 agent 프레임워크.

#### ㉘ ✦ Archivist AI for TTRPG (myarchivist.ai)
- D&D 캠페인 transcript·세션 노트를 STT → 구조화 요약 → 검색 가능 *campaign memory*로 변환. **DM을 대체하지 않고 보존·검색 보조**라는 입장을 명시.

#### ㉙ ✦ Memory Sandbox (Huang et al., 2023)
- 대화 메모리를 *조작 가능한 data object*로 노출 — 사용자가 agent의 기억을 편집/삭제하는 거버넌스.

#### ㉚ ◇ Google Arts & Culture × Gemini, "Ask a Painting" (2024)
- 박물관 소장품 metadata + LLM 결합으로 작품이 "1인칭으로 자기 역사를 이야기"하는 docent agent.

#### ㉛ ◇ Smithsonian × OpenAI / Met Museum chatbots (2023-)
- 박물관 챗봇이 collection knowledge를 *큐레이터 persona*로 발화. (1차 확인 못함; 본 영역의 알려진 trend.)

#### ㉜ ◇ "AI Storyteller" Steno AI / Storyflow / StoryGPT 류 startup
- LLM이 사용자의 family story·기억을 인터뷰해 archive로 보존. StoryFile의 텍스트형 변종.

#### ㉝ ◇ Reflect / Mem / Tana의 AI assistant
- 개인의 노트·일기를 학습해 *"당신의 외장 기억(second brain)"*으로 발화하는 personal archivist agent. 사용자가 만든 "사적 꼰대"의 prototype.

---

### 1D. Norm Enforcement / Moderation Agent

> 위 1A ⑥⑨⑩, 1B ㉓(scoping policy)와 부분 중복.

#### ㉞ ✦ LLM-as-Judge 패러다임 (Zheng et al., 2023; 다수 follow-up)
- 단일 LLM이 다른 agent 산출물을 normative criteria로 평가/제재. AI 꼰대-판관 구조의 표준 패턴.

#### ㉟ ◇ Constitutional AI (Anthropic, 2022) / Sparrow rules (DeepMind)
- "헌법"이라는 명시적 norm document에 따라 모델 행위를 self-critique·revise. 의인화는 약하지만 social code의 외부화에서 직접 선례.

#### ㊱ ◇ OpenAI Moderation API / Perspective API (Jigsaw, 2017-)
- 사회적 toxicity·hate speech의 자동 탐지·차단 — 의인화는 없으나 "디지털 사회의 자동 꼰대"로 기능.

#### ㊲ ✦ Norm Violation Detection in MAS (㉘=⑨ 동일)

---

## 2. 오픈소스 프로젝트 / 코드베이스

#### ㊳ ✦ AI Town (a16z + Convex, 2023; MIT 라이선스)
- **GitHub**: github.com/a16z-infra/ai-town
- 스택: Convex(서버리스 백엔드) + Pinecone(벡터) + OpenAI(LLM) + Pixi(렌더). Park et al. 논문의 JS/TS 포팅.
- **꼰대 시사점**: 가장 진입장벽이 낮은 prototyping 플랫폼. "마을의 가장 오래된 거주자"를 lore prompt로 단순 정의 가능. Yoko Li(a16z)는 *"누구나 자신의 세계를 만들고 그 안에 자기 기억을 부어넣을 수 있어야 한다"*라고 발언.

#### ㊴ ✦ a16z-infra/ai-town fork들 (Konisberg 등)
- Ollama 로컬 LLM 백엔드, Docker 셀프호스팅 지원 community fork.

#### ㊵ ✦ AgentSociety GitHub (②와 동일)
- v1(gRPC 기반 city sim) + v2(LLM-native).

#### ㊶ ✦ OASIS GitHub (③와 동일)
- MultiAgent4Collusion · CUBE(Unity3D) · MultiAgent4Fraud downstream 모듈.

#### ㊷ ✦ joonspk-research/generative_agents (Park et al. 원본)
- Smallville 환경을 PyGame 기반으로 재현. reflection memory reference 구현체.

#### ㊸ ◇ AutoGen / CrewAI / LangGraph의 "Role" template
- 커뮤니티가 "historian", "elder", "moderator" 등 role agent를 yaml/python으로 정의하는 패턴은 활발하지만, 공식 cultural role template은 부재 — **사용자가 첫 reference implementation을 만들 시장적 기회**.

#### ㊹ ◇ Inworld Character Engine open-source 부분 (TechCrunch 2023-08 보도, 후속 출시 시점 미확정)
- 일부 character creation 도구 open-source 공개 예고.

#### ㊺ ✦ AGI-Edgerunners/LLM-Agents-Papers, Shichun-Liu/Agent-Memory-Paper-List (GitHub 큐레이션)
- 본 보고서의 학술 사례를 발굴할 수 있는 메타-목록.

---

## 3. 게임 / 인터랙티브 내러티브

#### ㊻ ✦ Inworld AI (Mountain View, 2021; 누적 투자 $100M+)
- **Character Brain + Contextual Mesh + Real-Time AI** 3층 아키텍처. **Long-Term Memory** 기능으로 multi-session 동안 player 정보·관계·이전 대화의 contradictory 정보까지 자동 정리.
- **"4th Wall" 가드레일**: NPC가 게임 세계 lore 바깥(현실의 정치·시간·인물)을 언급 못하게 차단 — 일종의 *문화적 closure*를 자동 강제.
- 상용 통합: NetEase Games / Niantic 8th Wall / LG U+ / Alpine Electronics / Disney Accelerator(ILM Immersive "Droid Maker") / Xbox(Narrative Graph) / Stardew Valley·Skyrim·GTA V 커뮤니티 모드.

#### ㊼ ✦ Convai (Unity·Unreal SDK)
- "scene-aware" perception + voice. *"In persistent virtual worlds, AI characters can maintain continuity by remembering past interactions"* — 꼰대 Agent의 "세계 산증인" 역할의 직접적 상용화.

#### ㊽ ✦ Skyrim AI NPC mods (Inworld 기반, 2023-)
- Whiterun 노인 NPC들이 즉흥 대화로 *마을 역사*를 서술. "elder lore-keeper" 컨셉의 가장 직접적 구현.

#### ㊾ ✦ AIDungeonMaster.ai (2024-)
- D&D 5e rules engine + 무제한 세션 persistent campaign memory + creator marketplace. 일반 LLM 대비 "캠페인 기억"이 최대 차별점.

#### ㊿ ✦ AI Dungeon (Latitude, 2019-)
- 최초의 대중 LLM-DM. 한계로 "social consensus 없이 player가 임의 사실을 주장 가능"이라는 비평이 누적(Morpheus Log #3) — 사용자의 꼰대가 *"우리 세계엔 그런 거 없다"*고 거부하는 역할을 역설적으로 정당화.

#### (51) ✦ Friends & Fables (Discord 기반 그룹 AI DM, 2024)

#### (52) ◇ NovelAI / Character.AI / Replika / Pi (Inflection)
- 캐릭터 페르소나 + long-term memory를 결합한 character AI 플랫폼. Replika는 사용자와의 *친밀한 personal lore*를 누적 — 개인적 꼰대.

#### (53) ◇ Hidden Door (2024-)
- 사용자가 좋아하는 IP(소설·세계관)를 학습해 새 narrative를 generative하게 진행. *세계의 cultural rule*을 LLM이 reference하는 형식.

#### (54) ◇ Pantheon AI (2023-) / Inflection·Anthropic의 persona agent
- 역사적 인물·전문가 페르소나를 의인화한 대화 agent.

#### (55) ◇ Crusader Kings 3 / Stellaris AI 모드
- 세대간 lore 전수가 게임 메카닉인 작품. LLM mod로 *조상의 조언*을 동적 생성하는 community 실험.

#### (56) ◇ AI Village (Project Cambria, Microsoft Research 등 명명 다수 — 본 조사에서 명확한 식별 못함)
- emergent narrative 연구 라벨 — 검증 권장.

---

## 4. 예술 / 디자인 / Indigenous AI 프로젝트

#### (57) ✦ Indigenous Protocol and AI Working Group (IP-AI, 2019-)
- 주도: **Jason Edward Lewis**(Concordia, Cherokee/Hawaiian/Samoan), Angie Abdilla, Noelani Arista, Suzanne Kite 등 35명 (Kanaka Maoli, Palawa, Māori, Cree, Lakota, Cherokee, Coquille, Cheyenne, Crow).
- 2020 Position Paper: AI를 **"ancestors that we are making kin with"**의 관점에서 설계해야 한다는 입장. Lewis & Arista *"Making Kin with the Machines"* (Journal of Design and Science, 2018)가 이론적 토대.
- **꼰대 정렬도**: ★★★★★ — *AI를 elder/ancestor protocol-bound persona로 다룬다*는 점에서 가장 직접적 사상적 선례.
- 링크: indigenous-ai.net

#### (58) ✦ Hua Ki'i (IP-AI 산하 prototype, 2021)
- Caroline Running Wolf(Apsáalooke), Caleb Moses(Māori), Noelani Arista(Kanaka Maoli) 협업. 데이터 sovereignty와 cultural protocol을 코드 단계부터 내장한 윤리적 Indigenous AI prototype.

#### (59) ✦ Aboriginal Territories in Cyberspace (AbTeC), Initiative for Indigenous Futures
- Lewis 공동 디렉터. *Indigenous Futures Imaginary*를 디지털 매체(machinima·VR)로 보존·확장.

#### (60) ◇ Skawennati, "She Falls for Ages" (2017)
- machinima로 Iroquois 창조신화를 재해석한 Indigenous futurism 대표작.

#### (61) ◇ Stephanie Dinkins, "Conversations with Bina48" (2014-) / "Not The Only One" (N'TOO, 2017-)
- 흑인 가족 3대의 oral history를 데이터로 학습시킨 multigenerational memoir AI. **흑인 여성성을 의인화한 collective memory agent**의 가장 유명한 art piece. (Dinkins Studio, Knight Foundation 등 지원.)

#### (62) ◇ Refik Anadol, "Machine Hallucinations" / "Archive Dreaming" (2017-)
- SALT Research archive(170만 문서)를 t-SNE로 시각화한 *기억의 풍경*. agent persona는 없으나 *집합 기억의 visual personification*.

#### (63) ◇ Memo Akten, Mario Klingemann 등 generative artist
- training data를 *"기계의 무의식"*으로 다루는 비평적 art practice — 본 영역의 critical reference.

#### (64) ◇ Lauren Lee McCarthy, "LAUREN" (2017)
- 작가 본인이 Alexa를 대체하는 인간 home assistant 퍼포먼스 — *"누가 누구의 norm을 강제하는가"*를 묻는 critical art.

#### (65) ✦ *Real Life Magazine*, "Speaking for the Past" (비평 에세이)
- Dimensions in Testimony 비판: *"기계학습은 testimony를 listening이 아니라 interacting으로 환원하며, reparative promise를 충족하지 못한다"* — 꼰대 설계 시 필수 검토.

---

## 5. 교육 / 문화유산 보존

#### (66) ✦ Dimensions in Testimony (USC Shoah Foundation + USC ICT + Conscience Display, 2012 개념 / 2015 첫 설치)
- 메커니즘: 생존자 1인당 ~1,000-1,500개 질문에 대한 답변을 116-카메라 dome에서 volumetric 촬영 → NLP로 질문↔답변 매핑. 시스템 로그가 staff에 의해 검토되며 *"each question 시스템 품질이 향상"*.
- 현재 규모: Holocaust 생존자 다수, WWII 해방군 2명, Nanjing 학살 생존자 1명. 영어·스페인어·히브리어·독일어·만다린·러시아·스웨덴어. mobile rig로 글로벌 확대.
- 파트너 박물관: Illinois Holocaust Museum, Dallas Holocaust and Human Rights Museum, Museum of Jewish Heritage (NYC), Holocaust & Humanity Center (Cincinnati), Wassmuth Center for Human Rights, Virginia Holocaust Museum 등 다수.
- **꼰대 정렬도**: ★★★★★ — *한 개인 기억을 대화 가능한 persistent persona로 보존*하는 가장 발전된 사례.

#### (67) ✦ StoryFile (Stephen Smith, 2017-)
- Dimensions in Testimony의 *상용화 derivative*. Conversa 플랫폼.
- 사용 사례: National WWII Museum "Voices from the Front"; Japanese American National Museum(WWII 강제수용 생존자); "Big Sonia"(Holocaust 생존자 Sonia Warshawski); Marina Smith의 *자신의 장례식에서 대화하는 AI 아바타*(2022) — death-transcending memory의 극적 사례.
- 확장: William Shatner, Ed Asner 등 셀러브리티 / Terry Virts(NASA astronaut) 등 expert 보존.

#### (68) ✦ The Last Goodbye (USC Shoah Foundation + MPC VR, 2017)
- Pinchas Gutter의 Majdanek 강제수용소 방문을 VR 6DoF로 보존.

#### (69) ◇ The Forever Project, National Holocaust Centre and Museum (영국, 2019-)
- Dimensions in Testimony와 유사 메커니즘으로 영국 거주 생존자 보존.

#### (70) ◇ Te Hiku Media (Aotearoa NZ, 2018-)
- **Māori 언어 ASR**. Caleb Moses(IP-AI 멤버)가 관여. Kaitiakitanga 라이선스 — community sovereignty over data.

#### (71) ◇ Mukurtu CMS (Washington State Univ. + Warumungu community, 2007-)
- Aboriginal community가 cultural protocol(누가 무엇을 볼 수 있는가)을 메타데이터 layer로 강제하는 CMS. 꼰대 Agent의 *protocol-based access control*의 정확한 선례.

#### (72) ◇ Google Arts & Culture, "Talk to a Book" / Heritage on Edge (UNESCO 협업, 2018-)
- 위태로운 cultural site의 3D 보존 + AI 인터페이스.

#### (73) ◇ UNESCO Memory of the World 디지털 부속 프로젝트
- 등재 기록물에 대한 AI-enabled access agent (multiple regional initiatives; 본 조사 1차 확인 못함).

#### (74) ◇ The Anne Frank House VR / "Virtual Holocaust Survivor"
- VR + interactive AI를 결합한 museum tour 사례.

> **공통 한계**: (66)~(74)는 *개인 증언의 보존*에 집중하며, **사회적 schema(예: "한국 사회에서는 식사 자리에서 ~한다")** 같은 *집합적 메타데이터*의 보존을 위한 별도 형식은 산업화되어 있지 않음. **사용자의 꼰대 Agent가 메울 시장적·학술적 공백**이 바로 이 지점.

---

## 6. 이론적·비평적 문헌

| # | 문헌 | 핵심 |
|---|---|---|
| (75) ◇ | Halbwachs, *Les cadres sociaux de la mémoire* (1925) / *La mémoire collective* (1950) | 사용자가 의지하는 원전. 기억은 사회적 틀 안에서 재구성됨 |
| (76) ◇ | Jan Assmann, *Das kulturelle Gedächtnis* (1992) / "Communicative vs Cultural Memory" (2008) | Halbwachs 확장 — *cultural memory* 정초, ritual·canon이 매개 |
| (77) ◇ | Wegner (1987), *Transactive Memory: A Contemporary Analysis of the Group Mind* | 개인 기억이 그룹 차원으로 분산·접근 — 꼰대는 transactive memory의 지정 노드 |
| (78) ✦ | Lewis & Arista, *"Making Kin with the Machines"* (Journal of Design and Science, 2018) | Indigenous epistemology로 AI를 친족/조상으로 재정의 |
| (79) ✦ | Lewis et al., *Indigenous Protocol and AI Position Paper* (CIFAR, 2020) | protocol-bound AI 설계 가이드 (60+ pages) |
| (80) ✦ | *Real Life Magazine*, "Speaking for the Past" (2020경) | 알고리즘이 listening을 interacting으로 환원한다는 비평 |
| (81) ◇ | Wendy Hui Kyong Chun, *Updating to Remain the Same: Habitual New Media* (MIT Press, 2016) | habit/memory의 알고리즘적 재구성 비판 |
| (82) ◇ | Yuk Hui, *On the Existence of Digital Objects* (2016) | 디지털 객체의 ontogenesis — 사회적 메타데이터의 존재론 |
| (83) ◇ | José van Dijck, *Mediated Memories in the Digital Age* (Stanford, 2007) | 디지털 매체와 collective memory의 매개 |
| (84) ◇ | Andrew Hoskins (ed.), *Digital Memory Studies* (Routledge, 2017) | "connective memory" — 디지털 시대 기억 연구 표준 |
| (85) ✦ | Techrxiv 2025, *"Memory in LLM-based Multi-Agent Systems"* 서베이 | LLM-MAS에서 cultural memory의 enforcer agent 개념 정립 |
| (86) ◇ | Indigenous Data Sovereignty 운동 (CARE Principles, GIDA 2018) | data governance의 protocol화 — 꼰대 거버넌스의 토대 |

---

## 종합 비교 — '꼰대 Agent' 컨셉과의 정렬도 매트릭스

| 선행 사례 | Cultural metadata 명시성 | 단일 인격(persona) 의인화 | Norm 집행 권위 | Multi-session 보존 | 꼰대 정렬도 |
|---|---|---|---|---|---|
| Generative Agents (Park 2023) | 중 (개인 reflection) | △ (개인 25명) | × | ○ | ★★ |
| AgentSociety / OASIS | 약 (emergent) | × | × | ○ | ★★ |
| Schema-Guided Culture-Aware (2024) | **강 (schema=객체)** | △ | △ | ○ | ★★★★ |
| Cross/Haber/Yamins (2025) | 중 | × | **강** | ○ | ★★★ |
| Superego Agent (2025) | 약 (constitution) | **강** | **강** | ○ | ★★★★ |
| CultureBank + downstream | **매우 강 (DB)** | × | × | n/a | ★★★ (재료) |
| A-MEM (Zettelkasten) | 메타 | × | × | ○ | ★★★ (구조) |
| Dimensions in Testimony | 개인 testimony | **강 (단일 인물)** | × | ○ (영구) | ★★★★ |
| StoryFile | 개인 testimony | **강** | × | ○ | ★★★ |
| Indigenous AI / IP-AI | **강 (protocol)** | **강 (ancestor)** | △ (protocol) | ○ | ★★★★★ |
| Mukurtu CMS | **강 (access protocol)** | × (CMS) | **강 (강제)** | ○ | ★★★★ |
| Inworld Long-Term Memory | 약 (world lore) | **강** | × | ○ | ★★★ |
| Stephanie Dinkins N'TOO | **강 (가족史)** | **강** | × | ○ | ★★★★ |
| AI DM (AIDungeonMaster.ai) | 약 | **강 (DM persona)** | △ (rules) | ○ | ★★★ |

---

## 사용자 꼰대 Agent 설계로의 종합 시사점 (Synthesis)

1. **메모리 구조**: A-MEM의 Zettelkasten + MemoryOS의 3-tier(단·중·장기) + Park et al.의 reflection layer를 결합하되, **최상위 layer를 "cadre social"** — schema/norm/ritual의 추상화 노드로 명시 분리. Memory Sandbox의 *editable memory object* 패턴으로 거버넌스 확보.

2. **재료 데이터**: CultureBank(23K descriptor) + 한국 특화 corpus(속담, 예법서, 신문 칼럼, 가족 oral history). Schema-Guided Culture-Aware Simulation의 schema 정의 방식 차용.

3. **단일 인격 vs 집합 인격**: Dimensions in Testimony는 한 사람을, AgentSociety는 다수를 다룸. 꼰대는 *"가상의 한 사람이 사회 전체를 대변하는 metonymy"* — **Indigenous AI의 ancestor as composite + Stephanie Dinkins의 multigenerational AI**가 정확한 모델.

4. **권위와 sanction**: Cross-Haber-Yamins(2025)와 Superego Agent의 enforcement 메커니즘 통합. 제재 강도를 사용자 설정 가능(*"잔소리 레벨 슬라이더"*). LLM-as-Judge 패러다임을 보조 verifier로.

5. **거버넌스와 transparency**: *Real Life Mag* 비평을 진지하게 받아 — *"이 꼰대는 어느 사회를 대표하는가, 누가 결정했는가"*를 항상 표시할 transparency layer 의무화. **Mukurtu CMS의 protocol-based access control + IP-AI의 community sovereignty**를 직접 차용.

6. **시장·학술 공백**: 위 86개 항목 중 **"사회적 schema 자체를 의인화한 단일 persona + cross-cultural norm enforcement + transparent provenance + multi-session dialogic preservation"** 의 네 조건을 *동시에* 만족하는 프로젝트는 부재. **사용자의 꼰대 Agent는 이 교차점에 새 카테고리를 열 잠재력**이 있습니다.

7. **윤리적 함정**: (a) *대표성*(누가 한국 사회를 대변하는가), (b) *세대 권력*(꼰대가 청년의 새 norm을 억압하지 않는가), (c) *문화적 본질주의*(culture를 고정된 schema로 박제하지 않는가) — IP-AI position paper와 LiveCultureBench의 한계 명시 부분이 핵심 가드레일.

---

## 후속 조사 권장 영역 (본 보고서 범위 외)

본 조사는 검색 예산 제약으로 다음을 충분히 다루지 못했으며 별도 추적을 권장합니다:
- **한국 학술 사례**: KAIST·서울대 사회 시뮬레이션, 국립중앙박물관·국립한글박물관 AI docent, 한국학중앙연구원 — 한국적 '꼰대' 자체에 대한 사회학적 정의(generational/gendered/class 차원).
- **추가 indigenous language AI**: First Languages AI Reality(FLAIR), Common Voice의 endangered language branches.
- **Trevor Paglen, Kate Crawford, Caroline Sinders**의 dataset critique art.
- **Wendy Chun, Lev Manovich, Yuk Hui**의 machine memory 비평 이론 정독.
- **AutoGen / CrewAI / LangGraph**의 community role template GitHub 검색.
- **Replika의 long-term memory 실제 거동**, Character.AI personality persistence 검증.
- **Microsoft Recall / Project Cambria / Apple Intelligence**의 personal memory 거버넌스.

> 이 86개 사례 매트릭스를 출발점으로, **꼰대 Agent**는 *Halbwachs × Generative Agents × Indigenous Protocol × Norm Enforcement × Dialogic Testimony*의 5중 교차로에서 설계될 때 가장 학술적 신뢰성과 예술적 깊이, 그리고 실용적 차별성을 동시에 확보할 수 있을 것입니다.