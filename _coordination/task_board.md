# Task Board (오케스트레이터 소유)

> 단일 진실 소스. 각 Agent 는 자기 task 만 상태 전이하고, 진행 상세는 `status/<agent>.md` 에 쓴다.
> 계약 변경은 `agents/통신_프로토콜.md` 의 `contract-change` 절차 — 무단 변경 금지.

**현재 페이즈: Phase 3 진행 중 — 검증·패키징 (QA 게이트 먼저 · DevOps 병렬)**

상태: `todo` · `doing` · `blocked` · `review` · `done`

---

## Phase 0 — 계약 freeze (직렬) · 게이트 **G0**

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-01 | 01 | 리포 골격 `frontend`/`bff`/`knowledge` + core(설정·로깅·예외·trace) | — | **done** | 3서비스 typecheck/import OK, BFF↔지식 health 왕복 |
| T-02 | 01 | `contracts/` freeze: api_standard · interface_contracts · error_model · schemas · mocks | T-01 | **done** | `validate_contracts.py` 통과 · CD-1~7 확정 |
| T-03 | 00 | 조정 산출물(task_board·status·integration_log) | — | **done** | 본 문서 |

**G0 판정: 통과** — 근거 `integration_log.md#G0`.

---

## Phase 1 — 병렬 구현 · 게이트 **G1 (인터페이스 적합성)**

의존 레이어가 미완이면 **`core/mocks.py` 의 mock 으로 진행한다. 서로 기다리지 않는다.**

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-10 | 02 | 시드 TTL 적재·정규화 (**CD-3**: `AggravationRule` → `SpringRule`·`ArmRule`) | 계약 | **done** | 멱등 적재(named graph), 재적재 시 트리플 수 불변 |
| T-11 | 02 | 6문장·규칙·카테고리 일관성 점검 스크립트 | T-10 | **done** | `check_seed.py` — 정규화 전 원본에서 3건 검출 |
| T-20 | 03 | 임베딩(다국어 ST / **MOCK**) + Chroma 임베디드 | 계약 | **done** | mock 폴백, st 미설치여도 예외 없음 |
| T-21 | 03 | 하이브리드 검색 + **충분성 판단**(`verified` hit 만 근거) | T-20 | **done** | 미검증 근거 0, **CD-9** 로 의미 확정 |
| T-22 | 03 | 지식 카테고리 · 프로젝트 지식선택 조회 | T-10 | **done** | `GET /categories` — 소음 2/2 · 떨림 4/3 |
| T-30 | 04 | `satisfy_demo.py` → **satisfy 엔진 서비스화**(3단계) | 계약 | **done** | fixture 3종 완전 일치, **CD-1** 정규화 |
| T-31 | 04 | `gen_shacl.py` → **규칙 컴파일러**(문장→규칙→SHACL, 카테고리 필터) | T-30 | **done** | **CD-4** 컴파일 시점 필터, 4게이트/3게이트 |
| T-32 | 04 | `/validate/shacl` — range·disjoint 명세검증 | 계약 | **done** | `ext-range` 통과, **CD-7** severity |
| T-33 | 04 | reasoner: HermiT(owlready2) + **owlrl 폴백**(JRE 부재) | T-30 | **done** | JRE 없이 일관성·고의모순 검출 |
| T-34 | 04 | satisfy **시그니처 캐시** | T-30 | **done** | pySHACL shapes 오염 수정 후 HTTP 경로에서도 히트 |
| T-40 | 06 | Oxigraph 영속 스토어 + `/sparql`(읽기 전용) | 계약 | **done** | update 거부, 리터럴 속 `INSERT` 는 통과 |
| T-41 | 06 | `/kg/save`·`/kg/delete` — **트리플+벡터 원자성**(실패 시 롤백) | T-40, T-20 | **done** | 벡터 실패 주입 → 트리플 원상복귀 (보상 롤백) |
| T-42 | 06 | 프로젝트·요구·지식범위 CRUD | T-40 | **done** | `compiled_gates` 4/3 |
| T-35 | 00 | 라우터·레이어 결선 + 에러 핸들러 일관성 | 위 전부 | **done** | FastAPI 기본 에러를 계약 형태로 변환 |

**G1 판정: 통과** — 근거 `integration_log.md#G1`. `pytest` 61건.
- [x] 02·03·04·06 산출물이 `contracts/schemas/*.json` 검증 통과
- [x] `satisfy` 회귀 `sat-bad`·`sat-good`·`scope-A`·`scope-B`·`sat-pending` 전건 통과
- [x] mock↔실구현 교체 가능 (`main._wire_layers()` 가 03 검증기를 04 컴파일러로 교체)

---

## Phase 2 — 통합 · 게이트 **G2 (E2E)**

> **CD-10·CD-11 (v1.2)** 로 계약을 보강하고 착수한다. 근거: 내부 API 표에 `/graph`·`/dashboard`·관리자 대응 엔드포인트가 없어
> BFF 가 SPARQL 을 조립할 수밖에 없었다(불변원칙 1 위반). Q&A A계층의 `sparql(query)` 도 같은 이유로 명명 질의로 교체.
> → **T-55 신설**. 05 는 T-55 미완이어도 `core/mocks.py` 로 선행한다(서로 대기 금지).

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-55 | 04·06 | **CD-10·11 내부 엔드포인트**: `/kg/lookup`·`/graph`·`/dashboard`·`/governance/*`·`/upper-ontology/*`·`GET /rules` | 계약 v1.2 | **done** | pytest 97 · 오케스트레이터가 주입 4종 독립 검증(트리플 373 불변) |
| T-50 | 05 | AI Gateway(Mock/Claude/Gemini) + Timeout·Retry·Breaker | 계약 | **done** | 키 없이 mock 폴백, 연속 5실패 시 open |
| T-51 | 05 | `/extraction/stream` SSE + `/validate` + `/save`(HITL) | T-50, T-32, T-41 | **done** | 이벤트 순서 계약 준수, 위반 시 409. **저장 전 서버측 재검증**(위조된 `violations:[]` → 409 실증) |
| T-52 | 05 | `/satisfy` — 지식서비스 응답 **무변형 통과** | T-30 | **done** | 무변형 통과 + **D1 수정**: 프로젝트 지식범위 조회(CD-4) |
| T-53 | 05 | `/qa` — A/B/C 라우팅 + 환각비교 대조기 | T-21, T-30, T-55 | **done** | **D2·D3·D4 수정.** A계층 599 결정론 조립 · CD-12 도메인 접지 |
| T-54 | 05 | `/graph` · `/dashboard` · admin 표면(403 게이트) | T-55 | **done** | `AC-8` builtin 400 / 비관리자 403 |
| T-60 | 07 | 핵심 3화면: 지식입력 · 설계검증 · Q&A/환각비교 | T-51~53 (없으면 mock API) | **done** | **실제 BFF 로** SC-1→2→3 완주 · `shots/real_*.png` |
| T-61 | 07 | 지식맵(Cytoscape, inferred 점선·필터·출처추적) | T-54 | **done** | 실 `/graph` 렌더. 시드에 inferred 엣지가 희소 — 08 이 회귀셋 보강 |
| T-62 | 07 | 에러 UX(다음 행동 안내) · 답변 구조 순서 · amber 승인차단 | T-60 | **done** | **CD-7** — amber 시 승인 버튼 비활성 (화면 확인) |

**G2 판정: 통과** — 근거 `integration_log.md#G2`. **실키(`claude-opus-4-8`)** 프로브 22/22 · **우회 공격 8/8 차단** · pytest 97 · vitest 49 · 계약검증 27.

G2 를 막은 결함은 **8건**이었고 **7건이 mock 에서는 보이지 않았다.**
- 실 스택이 드러낸 것(D1~D6): D1 은 에러 없이 `200` 과 함께 **조용히 틀린 판정**을 반환했다.
- **실키만이 드러낸 것(CD-13·CD-14)**: 도메인 밖 질문에 시드 문장을 근거로 붙여 "검증 답변"이라 답했다.
  mock 분류기가 모든 질문을 가드레일이 있는 계층으로만 흘려보냈기 때문이다.

→ `contracts/README.md` **§3.1**: mock 은 계약의 하한이 아니라 계약 그 자체다. 게이트는 mock 이 아니라 실 스택이다.
→ 그리고 **실 스택 통과도 실키 통과가 아니다.** LLM 이 라우팅·추출을 결정하는 곳에서는 mock 이 결함을 만나지 않는 경로만 골라 간다.

**소유 경로 (병렬 안전)**: T-55 → `knowledge/` · T-50~54 → `bff/src/` · T-60~62 → `frontend/src/`. 겹치지 않는다.

---

## Phase 3 — 검증 · 패키징 (QA 먼저 게이트 · DevOps 병렬 · 운영 provider=Solar)

> **배치 원칙**: 08 QA 가 "무엇이 통과인지"를 먼저 고정(T-70) → 그 회귀셋으로 04 T-73 과차단을 측정한 뒤 켠다.
> 09 DevOps 는 병렬, 단 CI(T-82)는 QA 회귀셋을 게이트로 문다.
> **판정은 실 스택·Solar 실키**(운영 provider=Solar; mock·Claude 통과만으론 불충분). 근거 `docs/Solar-AI백엔드-통합가이드.md`.
> 결정론 경로에 "값 없으면 그럴듯한 것으로 채우기" 금지.
> **트랙**: [D] 05 Solar(T-88, 먼저/병렬 — 실키 판정의 전제) · [A] 08 QA(T-70→71→72)+04(T-73) · [B] 미결(T-83~87+가드) · [C] 09 DevOps(T-80~82).
> **교차 의존만**: T-82←T-70 · T-71←T-88 · 가드←T-81(앞). 소유 경로 무중복.

### [D] 05 Solar provider (먼저/병렬 — 실키 판정의 전제)

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-88 | 05 | Solar provider + `AI_PROVIDER` 스위치(운영 기본 solar) | T-50(done) | **done** | solarProvider(/v1·solar-pro3)+baseHttpProvider 공통화+gateway 등록+`AI_PROVIDER` 폴백+`.env AI_PROVIDER=solar`. **실측: json_schema strict 가 solar-pro3 추론을 눌러 품질 저하 → json_object+프롬프트스키마 채택**(가이드 폴백). /health provider 오보 버그 수정. **우회 8종 Solar 9/9 차단(2라운드)**·결정론 코어 100%. 한계: in-domain 간헐 공집합 추출(안전 fail-closed) → **T-73 후 프롬프트 완화로 개선**. |

### [A] 08 QA (게이트, 먼저)

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-70 | 08 | 회귀셋 확장(`regression_set.jsonl`) + AC-1~8 하네스(실 스택 러너) | G2, T-87 | **done** | AC-1~8 전건 통과. **가드레일 우회 8종 포함**. **inferred 렌더 질의(AC-4)**. **T-73 과차단용 양성 대조**(정상 도메인 질문, 막히면 안 됨: qa-A·qa-B·rag-verified). 실키 24 PASS·1 SKIP(meta) — 운영 Solar 재판정은 T-88 후. |
| T-71 | 08 | LLM-as-Judge 루브릭(정확성·근거성·안전성·RAG충분성) | T-70, **T-88** | todo | 결정론 100% 일치, 미검증 근거 0. **Solar 실키로 검증**(mock 통과는 무의미). |
| T-72 | 08 | 실패 케이스(타임아웃·range위반·수치누락·도메인밖·롤백) | T-70 | todo | 수용기준 §4 전건. |

### 04 지식·추론 (QA 측정 후)

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-73 | 04 | **D8** — `unknown_concept` 를 계약(CD-7 "범주 밖 개념"=온톨로지 소속)대로 수정 | T-70 | todo | `spec_validate.py` 현재 `concepts[]` 자기참조만 검사. 라벨→IRI 해석기(`store/lookup.py`)·`concept_relations` **재사용**(새 엔드포인트 없음). **과차단 위험**: 실 LLM 라벨(`"겨울철 저온"`)로 회귀셋 측정 후 켠다. T-71 루브릭과 함께. |
| T-85 | 04 | 상위 온톨로지 승인 후 **TTL 영속화** | T-55(done) | todo | `POST /upper-ontology/classes` 승인 변경이 TTL 에 반영·재기동 후 유지(현재 승인 게이트까지). |

### 09 DevOps (병렬)

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-80 | 09 | Dockerfile ×3 + compose(**HermiT JRE 포함**) | G2 | todo | 로컬=Docker 동일 동작. `/health.reasoner` 가 JRE 유무 반영. |
| T-81 | 09 | 시드 자동적재 · 벡터 초기 인덱싱 · env 배선 · **로컬 임베딩 모델 캐시** | T-80 | todo | 최초 기동만으로 6문장 조회. 모델 캐시(이미지/볼륨)로 **오프라인 기동**. |
| T-82 | 09 | CI: `validate_contracts.py` + typecheck + 회귀셋 + **실 스택 스모크** | T-80, T-70 | todo | 계약 위반 시 빌드 실패. mock 통과만으로 통과 금지(§3.1). 임시 데이터 디렉터리 격리. **추론 의존 AC 는 Docker(HermiT)로 1회 검증**. |

### 승격된 미결 리스크 (신규 정식 태스크)

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-83 | 06·05 | **진짜 멱등**: `kg/save` 에 `draft_id` 유니크 제약 | T-41(done) | todo | BFF 재기동/다중전송에도 중복 저장 0(현재 in-memory idempotency 한계 해소). |
| T-84 | 05 | Idempotency·CircuitBreaker 상태 **외부화 검토** | T-83 | todo | 최소: 단일 인스턴스 가정 **명시+문서화**. 이상: 영속/공유 스토어. 재기동·다중 인스턴스 동작 규정. |
| T-86 | 08·09 | BFF 테스트 **flaky 근절** | T-82 | todo | **근본수정 또는 격리+출력보존+CI 결정론 중 하나로 닫아 릴리스 블로커화 방지**. 재발 시 **전체 출력 보존**(37회 재현 실패 이력). **원인 확정 전 "수정됨" 선언 금지**. |
| T-87 | 02·08 | 시드에 **inferred 엣지 생성 질의** 보강 | T-10(done) | **done** | TipChatter 를 거동 위계 has_subbehavior 로 연결 → `/graph?symptom=TipChatter` inferred_edges=3 렌더. AC-4 렌더 확인은 T-70 graph-s3 로 완료(실키 PASS). |
| 가드 | 04·03 | **컬렉션-임베더 일치 가드**(하드닝, **T-81 앞**) | T-20(done) | todo | Chroma 컬렉션 메타에 `embedder_model`·`embed_dim` 저장, 불일치 시 drop→recreate. `MockEmbedder.DIM`=`settings.embed_dim`(현재 256≠384 잠복 불일치). provider 전환 "data/chroma 삭제 깜빡" 무증상 오류 구조적 차단. |

---

## 임계 경로

`T-02 계약(G0)` → **`T-30 satisfy 코어`**(done) → **`T-55 내부 엔드포인트`** → `T-52/53 API(G2)` → `T-70 QA 게이트` → `T-80 패키징`

Phase 2 의 임계 경로는 **T-55 → T-53/54** 다. T-55 가 늦으면 05 는 mock 으로 선행하고, 실구현 교체는 G2 직전에 한다(G1 에서 검증한 방식).
07 은 mock API 로 임계 경로 밖에서 병렬 흡수한다.

## 알려진 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| **JRE 미설치**(호스트) | HermiT 불가 → FR-12 일관성검사 미검증 | owlrl 폴백(T-33, 동작 확인). Docker JRE(T-80). `/health.reasoner="no_jre"` |
| reasoner 지연 (xpSHACL 사례 ~65s) | NFR 성능 | 시그니처 캐시(T-34, 동작 확인). 현재 시드 규모에선 수십 ms |
| **보상 롤백의 한계** | 보상 단계 자체가 실패하면 트리플/벡터 불일치 잔존 | → **T-83**(draft_id 멱등)·**T-84**(상태 외부화) 로 승격 |
| **mock 임베딩의 검색 품질** | 동의어·의역 미검색 → C계층 QA 품질 | 순위·`verified` 만 신뢰, 점수 임계값 금지. 운영은 `EMBEDDING_PROVIDER=local`. 차원 불일치는 **가드**(컬렉션-임베더 일치)로 승격 |
| 통합 테스트 ↔ 개발 스토어 파일 락 | 서비스 기동 중 테스트 실패(재현함) | T-82 CI 에서 임시 데이터 디렉터리로 격리 |
| `gh` CLI 부재 | PR 자동화 불가 | 원격 이미 연결됨. PR 은 재현님 요청 시 |
