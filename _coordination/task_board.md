# Task Board (오케스트레이터 소유)

> 단일 진실 소스. 각 Agent 는 자기 task 만 상태 전이하고, 진행 상세는 `status/<agent>.md` 에 쓴다.
> 계약 변경은 `agents/통신_프로토콜.md` 의 `contract-change` 절차 — 무단 변경 금지.

**현재 페이즈: Phase 2 착수 대기 (G0·G1 통과, 승인 요청 중)**

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

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-50 | 05 | AI Gateway(Mock/Claude/Gemini) + Timeout·Retry·Breaker | 계약 | todo | 키 없이 mock 폴백, 연속 5실패 시 open |
| T-51 | 05 | `/extraction/stream` SSE + `/validate` + `/save`(HITL) | T-50, T-32, T-41 | todo | 이벤트 순서 계약 준수, 위반 시 409 |
| T-52 | 05 | `/satisfy` — 지식서비스 응답 **무변형 통과** | T-30 | todo | BFF 가 판정 필드를 재해석하지 않음 |
| T-53 | 05 | `/qa` — A/B/C 라우팅 + 환각비교 대조기 | T-21, T-30, T-40 | todo | `qa-A`·`qa-B-compare`·`qa-C-insufficient` 통과 |
| T-54 | 05 | `/graph` · `/dashboard` · admin 표면(403 게이트) | T-40 | todo | `AC-8` builtin 400 / 비관리자 403 |
| T-60 | 07 | 핵심 3화면: 지식입력 · 설계검증 · Q&A/환각비교 | T-51~53 (없으면 mock API) | todo | SC-1→2→3 화면에서 완주 |
| T-61 | 07 | 지식맵(Cytoscape, inferred 점선·필터·출처추적) | T-54 | todo | `AC-4` 재현 |
| T-62 | 07 | 에러 UX(다음 행동 안내) · 답변 구조 순서 · amber 승인차단 | T-60 | todo | **CD-7** — amber 시 승인 버튼 비활성 |

**G2 통과 조건**: SC-1 → SC-2 → SC-3 가 화면에서 처음부터 끝까지 동작.

---

## Phase 3 — 검증 · 패키징

| id | owner | task | deps | 상태 | DoD |
|---|:--:|---|---|:--:|---|
| T-70 | 08 | 회귀셋 확장(`regression_set.jsonl`) · 수용기준 AC-1~8 | 상시 | todo | 전건 통과 |
| T-71 | 08 | LLM-as-Judge 루브릭(정확성·근거성·안전성·RAG충분성) | T-70 | todo | 결정론 100% 일치, 미검증 근거 0 |
| T-72 | 08 | 실패 케이스(타임아웃·range위반·수치누락·도메인밖·롤백) | T-70 | todo | 수용기준 §4 전건 |
| T-80 | 09 | Dockerfile ×3 + compose(**HermiT JRE 포함**) | G2 | todo | 로컬=Docker 동일 동작 |
| T-81 | 09 | 시드 자동적재 · 벡터 초기 인덱싱 · env 배선 | T-80 | todo | 최초 기동만으로 6문장 조회 가능 |
| T-82 | 09 | CI: `validate_contracts.py` + typecheck + 회귀셋 | T-80 | todo | 계약 위반 시 빌드 실패 |

---

## 임계 경로

`T-02 계약(G0)` → **`T-30 satisfy 코어`** → `T-52/53 API(G2)` → `T-70 QA 게이트` → `T-80 패키징`

02·03·06·07 은 임계 경로 밖에서 병렬 흡수한다. **T-30 이 늦어지면 전체가 늦어진다** — 04 에 우선 지원.

## 알려진 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| **JRE 미설치**(호스트) | HermiT 불가 → FR-12 일관성검사 미검증 | owlrl 폴백(T-33, 동작 확인). Docker JRE(T-80). `/health.reasoner="no_jre"` |
| reasoner 지연 (xpSHACL 사례 ~65s) | NFR 성능 | 시그니처 캐시(T-34, 동작 확인). 현재 시드 규모에선 수십 ms |
| **보상 롤백의 한계** | 보상 단계 자체가 실패하면 트리플/벡터 불일치 잔존 | 재기동 시 정합성 스윕 or outbox 도입 검토(Phase 3) |
| **mock 임베딩의 검색 품질** | 동의어·의역 미검색 → C계층 QA 품질 | 순위·`verified` 만 신뢰, 점수 임계값 금지. 운영은 `EMBEDDING_MODE=st` |
| 통합 테스트 ↔ 개발 스토어 파일 락 | 서비스 기동 중 테스트 실패(재현함) | T-82 CI 에서 임시 데이터 디렉터리로 격리 |
| `gh` CLI 부재 | PR 자동화 불가 | 원격 이미 연결됨. PR 은 재현님 요청 시 |
