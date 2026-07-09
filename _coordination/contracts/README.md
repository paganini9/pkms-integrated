# 계약 (contracts) — v1 freeze

> **G0 게이트 산출물.** 이 디렉터리의 내용은 **고정(freeze)** 이며, 무단 변경은 통합 실패의 주원인이다.
> 변경은 `_coordination/agents/통신_프로토콜.md`의 `contract-change` 절차(영향분석 → 승인 → 버전업 → 전체 통지)를 따른다.
> 근거 문서: `docs/기술_설계_명세서.md` §3·§5·§6 · `docs/개발_요구사항_명세서.md` · `docs/수용기준_및_테스트_시나리오.md`

| 파일 | 내용 | 소비자 |
|---|---|---|
| `api_standard.md` | BFF 외부 API (`/api/v1`) — 엔드포인트·요청·응답·SSE | 05 백엔드(구현) · 07 프론트(소비) · 08 QA |
| `interface_contracts.md` | BFF↔지식서비스 내부 HTTP 계약 + 레이어 Protocol(타입 시그니처) | 02·03·04·05·06 |
| `error_model.md` | 공통 에러 코드·HTTP 매핑·사용자 메시지 분리 | 전원 |
| `schemas/*.json` | 위 계약의 JSON Schema (기계 검증용) | 05·07·08 |
| `mocks/*.json` | 계약을 만족하는 고정 fixture (병렬·모의 개발용) | 전원 |

## 0. 버전

- **v1** (2026-07-10 freeze). 이후 변경은 `v1.1`, `v2` 로 표기하고 이 표에 이력을 남긴다.

| 버전 | 일자 | 변경 | 영향 Agent |
|---|---|---|---|
| v1 | 2026-07-10 | 최초 freeze (G0) | — |

## 1. 불변 원칙 (계약보다 상위)

1. **레이어 분리** — 지식·추론·RAG는 `knowledge/`(Python)에만 존재한다. `bff/`(Node)는 오케스트레이션·LLM 생성·SSE만 한다. BFF는 RDF/SPARQL/SHACL을 직접 다루지 않는다.
2. **내부 구조 비노출** — 지식서비스는 내부망 전용. 외부에 노출되는 표면은 BFF `/api/v1` 뿐이다. 응답에 트리플·블랭크노드·내부 그래프 구조를 그대로 흘리지 않는다.
3. **결정론 우선** — `satisfy`·명세검증의 **판정 주체는 reasoner/SHACL**이다. LLM은 생성(추출 초안·문장 파싱·자연어 답변)만 한다. 판정 필드(`satisfies`, `conforms`, `violations`)는 절대 LLM 출력으로 채우지 않는다.
4. **HITL 게이트** — `/extraction/save`, 상위 온톨로지 저장, 규칙 변경 저장, satisfy 채택은 `approved: true` 없이는 수행되지 않는다.
5. **MOCK 우선** — API 키가 없어도 전 흐름이 Mock으로 끝까지 동작해야 한다(`AI_MOCK_MODE=true`, `EMBEDDING_MODE=mock`).
6. **시크릿 분리** — 키는 프로세스 환경변수로만. 코드·`.env`·git·이미지·로그(마스킹)에 금지.

## 2. 계약 결정 (Contract Decisions) — 명세의 모호함을 여기서 확정

명세 간 표기가 갈리는 지점을 G0에서 확정한다. 구현·테스트는 아래를 따른다.

### CD-1. `violations` 정규화 (satisfy)
`수용기준_및_테스트_시나리오.md`가 두 표기를 함께 쓴다 — AC-2는 `S1·S3·S4·S6`, 회귀셋 `scope-A`는 `["S1","S3,S5","S4","S6"]`. 둘 다 만족시키기 위해 응답에 **두 필드**를 둔다.

- `violation_bases: string[]` — 위반한 SHACL 게이트의 **원본 basis 문자열** 그대로. 예 `["S1","S3,S5","S4","S6"]`
- `violations: string[]` — 위 basis를 콤마 분해한 뒤 **극성이 `cause`·`aggravate`인 문장만** 남기고 정렬·중복제거. 예 `["S1","S3","S4","S6"]`
  - `S5`는 극성 `mitigate`(해소 근거)이므로 위반 목록에서 제외된다. 이것이 AC-2와 회귀셋을 동시에 성립시키는 유일한 해석이다.

### CD-2. 문장 코드 vs IRI
API는 사람이 읽는 **문장 코드**(`S1`…`S6`)와 **`iri`**(`http://ex.org/domain#S1`)를 함께 실어 보낸다. 프론트·회귀셋은 코드로 단언하고, 지식맵·출처추적은 IRI를 쓴다. 코드는 `dom:sentenceNo`가 아니라 `dom:basis`/로컬네임 기준이다.

### CD-3. 규칙 식별자
`m1_wiper.ttl`은 `AggravationRule`(S4+S6 묶음), `rules.ttl`은 `SpringRule`·`ArmRule`(분리)로 표기한다. **단일 진실원은 `rules.ttl`**(구조화 DesignRule)이며, API가 노출하는 규칙 id는 `rules.ttl` 기준(`NoiseRule`·`SiliconeRule`·`ChatterRule`·`SpringRule`·`ArmRule`)이다. 02 데이터 Agent가 시드 적재 시 `m1_wiper.ttl`의 `AggravationRule` 표기를 `rules.ttl`에 맞춰 정규화한다.

### CD-4. 프로젝트 지식범위의 적용 지점
`categories` 필터는 **규칙 컴파일 시점**에 적용한다(`compile_rules(rules, categories)`). satisfy 호출은 프로젝트가 선택한 카테고리로 컴파일된 SHACL 게이트 집합만 사용한다. 판정 후 필터링(post-filter)은 금지 — 결과가 달라진다.

### CD-7. `severity`의 의미 (amber ↔ 저장 차단)
AC-1은 range 위반을 "**amber 경고**로 표시"라 하고, 실패 케이스 표(수용기준 §4)는 같은 위반에 "**저장 차단** + 수정 유도(HITL)"를 요구한다. amber를 "저장 가능한 경고"로 읽으면 두 문장이 충돌한다. 확정:

- **`severity: "violation"`** — UI **amber**로 표시하고 **저장을 차단**한다(`409 GUARDRAIL_BLOCKED`). `causes_range`·`disjoint`·`shacl_constraint`가 여기 속한다. AC-1의 "amber 경고"가 이것이다.
- **`severity: "warning"`** — UI 정보 표시, **저장 허용**. `missing_required`(satisfy 판정 보류 사유)·`unknown_concept`(범주 밖 개념 → 해당 항목만 드롭)가 여기 속한다.

즉 amber는 "치명적이지 않아 보이는 색"이 아니라 **"고쳐야 저장된다"는 신호**다. 프론트는 amber 항목이 하나라도 있으면 승인 버튼을 비활성화한다.

### CD-5. 역할(Role)
MVP는 Mock-Role. 요청 헤더 `X-Role: engineer|admin`. 관리자 전용 표면(`/upper-ontology/*`·`/rules/*`·`/governance/*`)은 `admin`이 아니면 `403 FORBIDDEN`. 배포 시 JWT로 교체하되 **계약(헤더 의미)은 불변**.

### CD-6. trace_id
모든 응답 본문(에러 포함)과 모든 SSE `done`/`error` 이벤트는 `trace_id`를 포함한다. 요청 헤더 `X-Trace-Id`가 있으면 그대로 전파(BFF→지식서비스), 없으면 BFF가 생성한다.

## 3. mock fixture 사용 규약

- `mocks/`의 JSON은 **계약을 만족하는 정답 샘플**이다. 각 Agent는 의존 레이어가 미완이면 이 fixture를 반환하는 mock 구현으로 선행한다.
- fixture 변경은 계약 변경이다(위 절차 필요). 테스트가 fixture를 직접 참조하므로 임의 수정 금지.
- `mocks/regression_set.jsonl`은 08 QA Agent가 확장하는 **시드**다(수용기준 §3 원문 + 계약 정규화 반영).
