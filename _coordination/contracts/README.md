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
| v1.1 | 2026-07-10 | **CD-8** — `Design` 의 `length_mm`·`spring_n`·`arm_shape`·`env` 를 선택(nullable)으로. 필수였으면 "판정 보류"에 도달할 수 없었다 | 04·05·07·08 |
| v1.1 | 2026-07-10 | **CD-9** — RAG `verified` = 지식범위로 컴파일된 규칙(mitigate 포함). 게이트 기준이면 AC-2 의 근거 S2·S5 가 사라진다 | 03·05·08 |
| v1.2 | 2026-07-10 | **CD-10** — `/graph`·`/dashboard`·거버넌스·상위온톨로지의 **내부 엔드포인트 신설**. 없으면 BFF 가 SPARQL 을 조립해야 해 불변원칙 1 이 깨진다 | 04·05·06·07 |
| v1.2 | 2026-07-10 | **CD-11** — `KnowledgeClient.sparql(query)` 폐기 → **명명 질의(named query)** `POST /kg/lookup`. BFF 가 쿼리 문자열을 만들 수 없다 | 05·06 |
| v1.3 | 2026-07-10 | **CD-12** — `insufficient_evidence` 가 도달 불가능했다. `sufficient` 에 **도메인 접지(grounding)** 조건 추가 | 03·05·08 |
| v1.4 | 2026-07-10 | **CD-13** — 접지를 라우팅 **뒤**에 두어 라우팅이 우회로가 되었다. 각 계층이 입력을 **날조**한다. 전 계층 fail-closed | 05·07·08 |
| v1.5 | 2026-07-10 | **CD-14** — 근거 없는 `answer()` 호출이 곧 환각 답변이다. 검증답변과 LLM단독답변의 **호출 분리** | 05·07·08 |

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

### CD-9. RAG `verified` 의 의미 — 게이트가 아니라 **지식범위** — v1.1
`interface_contracts.md` §1.1은 `verified`를 "그 문장이 파생한 규칙이 SPARQL/SHACL 검증을 통과했는가"라 썼다. 이를 "SHACL 게이트로 컴파일되었는가"로 구현하면 **`mitigate` 규칙이 전부 미검증으로 떨어진다** — 해소 규칙은 원인의 여집합이라 게이트를 만들지 않기 때문이다.

그런데 AC-2는 설계 B가 만족한다는 근거로 **S2**(실리콘 → 소음 해소)와 **S5**(세단 550mm 무해)를 요구한다. 둘 다 `mitigate` 다. 게이트 기준으로 판정하면 정답 근거가 답변에서 사라진다.

확정: **`verified` = 그 문장의 규칙이 프로젝트 지식범위로 컴파일된 규칙 집합(`rule_ids`)에 속하는가.**
- `mitigate` 포함. 게이트 여부는 `verified` 와 무관하다.
- 미검증이 되는 경우: 알 수 없는 규칙 · **프로젝트 지식범위 밖**(CD-4) · 규칙 컴파일 실패.
- 답변 근거(`sources`)에는 `verified: true` 만 싣는다(루브릭 "미검증 근거 0"). `sufficient` = `verified` hit ≥ 1.

### CD-8. `Design` 의 수치는 선택이다 (판정 보류가 도달 가능해야 한다) — v1.1
수용기준 §4는 "satisfy 수치 누락 → SHACL 필수속성 경고, **판정 보류**"라 하고, `error_model.md` §3은 이를 `200 satisfies:null` 로 못박았다. 그런데 v1 의 `Design` 스키마는 `length_mm`·`spring_n`·`arm_shape` 를 **필수**로 두었다. 필수라면 결측 요청은 `422 VALIDATION_ERROR` 에서 걸려 **판정 보류 경로에 영원히 도달하지 못한다.**

확정: `material`·`vehicle` 만 필수(설계를 식별하는 최소 정보). 나머지 수치·형상·환경은 **선택(nullable)**.
- 결측 시 → `satisfies: null`, `pending_reason: "missing_required"`, `steps[1].warnings[]` 에 `missing_required`(severity `warning`) 를 싣는다.
- `warning` 이므로 저장·입력을 막지 않는다(CD-7). 다만 **확정 판정으로 승격하지 않는다** — 부분 정보로 ✅/⛔ 를 말하지 않는다는 뜻이다.

### CD-7. `severity`의 의미 (amber ↔ 저장 차단)
AC-1은 range 위반을 "**amber 경고**로 표시"라 하고, 실패 케이스 표(수용기준 §4)는 같은 위반에 "**저장 차단** + 수정 유도(HITL)"를 요구한다. amber를 "저장 가능한 경고"로 읽으면 두 문장이 충돌한다. 확정:

- **`severity: "violation"`** — UI **amber**로 표시하고 **저장을 차단**한다(`409 GUARDRAIL_BLOCKED`). `causes_range`·`disjoint`·`shacl_constraint`가 여기 속한다. AC-1의 "amber 경고"가 이것이다.
- **`severity: "warning"`** — UI 정보 표시, **저장 허용**. `missing_required`(satisfy 판정 보류 사유)·`unknown_concept`(범주 밖 개념 → 해당 항목만 드롭)가 여기 속한다.

즉 amber는 "치명적이지 않아 보이는 색"이 아니라 **"고쳐야 저장된다"는 신호**다. 프론트는 amber 항목이 하나라도 있으면 승인 버튼을 비활성화한다.

### CD-5. 역할(Role)
MVP는 Mock-Role. 요청 헤더 `X-Role: engineer|admin`. 관리자 전용 표면(`/upper-ontology/*`·`/rules/*`·`/governance/*`)은 `admin`이 아니면 `403 FORBIDDEN`. 배포 시 JWT로 교체하되 **계약(헤더 의미)은 불변**.

### CD-6. trace_id
모든 응답 본문(에러 포함)과 모든 SSE `done`/`error` 이벤트는 `trace_id`를 포함한다. 요청 헤더 `X-Trace-Id`가 있으면 그대로 전파(BFF→지식서비스), 없으면 BFF가 생성한다.

### CD-14. 근거 없는 `answer()` 호출이 곧 환각 답변이다 — 두 호출을 분리한다 — v1.5

**CD-13 수정 직후 실키 검증에서 발견.** 가드레일 하나를 고치자 같은 병이 옆에서 재발했다.

`"중형 SUV에 고무 600mm 써도 될까?"` (스프링·암형상 미지정) →
```
layer=B  insufficient_evidence=false  sources=[]
verified_answer.text = "## 답변 … 일반적인 설계 지식에 기반한 답변입니다 …"
verified_answer.determinism = "satisfy"
```
`parseDesign` 이 (CD-13 대로) 값을 지어내지 않으니 `spring_n`·`arm_shape` 가 없고, satisfy 는 **CD-8 판정 보류**를 반환한다.
그러면 `violations` 가 비고 → `sources` 가 비고 → `gw.answer(question, [])` 가 호출된다.

**그런데 `answer(q, [])` 는 환각비교의 `llm_answer` 를 만드는 바로 그 호출이다** — 시스템 프롬프트가
"근거 없이 일반 지식만으로 답하라"로 갈린다. 즉 **미검증 LLM 답변에 `determinism:"satisfy"` 라벨을 붙여 내보냈다.**
`llm_answer` 와 `verified_answer` 를 **같은 함수로** 만든 것이 화근이다. 근거가 비는 순간 둘이 같아진다.

확정:

1. **`verified_answer.text` 는 `sources` 가 비면 LLM 이 생성하지 않는다.** 결정론 문자열만 쓴다
   ("명세 근거 없음" 또는 "판정 보류 — 수치 누락: …"). 예외 없다.
2. **B계층 판정 보류**(`satisfies === null`) → `insufficient_evidence: true`, `sources: []`,
   결정론 텍스트로 **무엇이 없어서 판정을 못 하는지** 알린다. 확정 답변 금지.
3. **호출을 이름으로 분리한다.** `AIProvider` 에서
   - `answer(question, sources)` — **`sources` 가 비면 throw.** 검증 답변 전용.
   - `llmOnlyAnswer(question)` — 무근거 단독 답변 전용. **환각비교의 `llm_answer` 에만 쓴다.**

   같은 함수를 두 목적에 쓰면 언젠가 또 섞인다. 타입으로 갈라 놓는다.

> **원칙**: 가드레일은 도달 가능(CD-8·CD-12)하고 우회 불가능(CD-13)해야 하며,
> **막다른 길에서 조용히 LLM 으로 흘러내려서는 안 된다.** 근거가 없으면 답하지 않는다 — 답을 *만들어내지* 않는다.

### CD-13. 가드레일은 라우팅보다 **앞**에 있어야 한다 — 전 계층 fail-closed — v1.4

**실키(Claude) 검증에서 실행으로 발견.** mock 분류기가 가리고 있었다.

| 질문 | 계층 | 실제 응답 |
|---|:--:|---|
| "타이어 공기압은 얼마로 맞춰야 하나요?" | **A** | `insufficient:false`, 근거 `S1` — *겨울철 고무 소음* 문장으로 답한다 |
| "엔진 오일 교환 주기는?" | **A** | 동일하게 `S1` |
| "자전거 체인에 실리콘 윤활유 써도 될까?" | **C** | `insufficient:false`, 근거 **시드 문장 6개 전부** |
| "노트북에 알루미늄 700mm 써도 될까?" | **B** | 확정 판정 + 근거 8개(문장 4·규칙 4) |

CD-12 의 도메인 접지는 **C계층 안에만** 있었다. 그런데 계층은 **LLM 분류기가 고른다.**
분류가 A 나 B 로 가면 접지는 실행조차 되지 않는다 — **가드레일 뒤에 라우팅을 두면 라우팅이 우회로가 된다.**

더 나쁜 것은 각 계층이 **없는 입력을 지어낸다**:
- **A** — `mapNamedQuery` 에 무조건 폴백이 있다(어떤 질문이든 `symptom_causes(Noise)`). `rows` 가 절대 비지 않으므로 `insufficient` 가 영영 발화하지 않는다.
- **B** — `parseDesign` 이 기본 설계를 날조한다(`Rubber/600mm/8N/simple/MidSizeSUV/Winter`). 노트북 질문에도 완전한 설계가 만들어져 **확정 판정**이 나온다.
- **C** — 접지가 "알려진 개념 ≥ 1" 이라 `실리콘` 하나만 스쳐도 통과한다. `자전거`·`체인` 이 미지 개념인데도 6개 문장이 근거로 붙는다.

실제 Claude 는 답변 **문장**에서는 "제공된 근거만으로는 답변할 수 없습니다"라고 스스로 물러섰다.
**그러나 계약 필드는 거짓말을 했다** — `insufficient_evidence:false`, `sources:[S1,…]`. 프론트는 이를 "검증 답변 + 출처"로 렌더한다.
**가드레일이 LLM 의 선의에 의존하고 있었다.** 이것은 결정론 우선(불변원칙 3) 위반이다.

확정:

1. **접지는 라우팅보다 먼저 실행한다.** `/qa` 진입 직후 질문을 `gateway.extract` → `POST /validate/shacl` 로 접지 판정한다.
   **알려진 개념이 0 이면 계층과 무관하게** `insufficient_evidence:true`, `sources:[]`, "명세 근거 없음".
2. **각 계층은 fail-closed 다. 입력을 지어내지 마라.**
   - **A** — 화이트리스트 명명 질의에 **매칭되지 않으면 폴백하지 않는다**. 매칭 실패 → `insufficient_evidence:true`. 기본 질의 금지.
   - **B** — `parseDesign` 은 `material`·`vehicle` 을 **날조하지 않는다**. 질문에서 얻지 못하면 **CD-8 판정 보류**(`satisfies:null`, `pending_reason:"missing_required"`)로 간다. 기본값 금지.
   - **C** — 근거를 붙이려면 질문의 개념이 **전부 알려진 개념**이어야 한다(`unknown_concept` 가 1건이라도 있으면 `insufficient`). 자유질의로 문장을 생성하는 계층이므로 가장 보수적으로 닫는다.
3. **`sources` 는 `insufficient_evidence:true` 일 때 반드시 빈 배열이다.** 근거 없이 답하지 않는다는 뜻은 *근거를 붙이지 않는다*는 뜻이기도 하다.

> **원칙**: 가드레일이 **도달 가능**해야 한다는 것(CD-8·CD-12)만으로는 부족하다. **우회 불가능**해야 한다.
> 그리고 판정 경로의 어떤 단계도 **없는 입력을 지어내서는 안 된다** — 지어낸 입력은 결정론 엔진을 통과해 *권위 있는 거짓*이 된다.

### CD-12. `insufficient_evidence` 는 도달 불가능했다 — 도메인 접지를 추가한다 — v1.3

**G2 통합에서 실행으로 발견.** 도메인 밖 질문("타이어 공기압은 얼마로 맞춰야 하나요?")을 `/qa` 에 넣으면
`insufficient_evidence: false` 에 시드 문장 **6개 전부**가 근거로 실렸다. 점수는 5건이 `0.000` 이었다.

원인은 구현이 아니라 **정의**다. CD-9 는 `sufficient` = `verified` hit ≥ 1 이라 했고, `verified` = "프로젝트 지식범위로
컴파일된 규칙에 속하는가" 다. 시드 문장은 전부 지식범위 안이므로 `verified: true` 이고, 검색은 질문과 무관하게 언제나
상위 `k` 건을 돌려준다. 따라서 **`sufficient` 는 항상 참이고 "명세 근거 없음" 분기는 절대 발화하지 않는다.**
`verified` 는 *권위*(이 문장을 근거로 써도 되는가)를 재는 축이지 *관련성*(이 질문에 답하는가)을 재는 축이 아니다.
두 축을 하나로 쓴 것이 결함이다. CD-8 과 같은 종류다 — **가드레일이 도달 불가능하면 없는 것과 같다.**

확정: `insufficient_evidence` = `도메인 접지 실패` **OR** `verified hit == 0`.

- **도메인 접지**: C계층 질문을 추출기(`gateway.extract`, temperature 0)에 통과시켜 개념을 뽑고, 그 개념들을
  기존 `POST /validate/shacl` 로 검증한다. **인식된 개념이 0 이거나 전부 `unknown_concept` 이면 도메인 밖**이다.
  → `insufficient_evidence: true`, `sources: []`, `verified_answer.text` 는 "명세 근거 없음".
- 새 엔드포인트를 만들지 않는다. `unknown_concept`(CD-7 의 `warning`) 는 이미 이 판정을 위해 존재한다.
- **점수 임계값은 여전히 금지**다(mock 임베딩의 절대 점수는 의미가 없다). 접지는 개념 사전 조회이지 유사도 컷이 아니다.
- `verified` 의 의미(CD-9)는 **바뀌지 않는다**. 관련성 축을 하나 더 얹는 것이다.

> 회귀 `qa-C-insufficient` 는 이 분기가 실제로 발화함을 단언해야 한다. 발화하지 않으면 08 QA 게이트를 통과시키지 않는다.

### CD-10. 조회·관리자 표면에는 내부 엔드포인트가 필요하다 — v1.2
`api_standard.md` §4.6·§4.8·§4.9 는 BFF 외부 표면 `/graph`·`/dashboard`·`/governance/concepts*`·`/upper-ontology/*`·`GET /rules` 를 요구한다. 그런데 `interface_contracts.md` §1 내부 API 표에는 대응 엔드포인트가 **없다**. 이 상태로 구현하면 BFF 가 SPARQL 문자열을 조립해 노드·엣지·통계를 만들 수밖에 없고, 이는 **불변원칙 1**(BFF는 RDF/SPARQL을 다루지 않는다) 위반이다. 원칙은 계약보다 상위다 → 내부 엔드포인트를 신설한다. 상세는 `interface_contracts.md` §1.2.

BFF 의 역할은 **역할 게이트(CD-5) + 무변형 통과**다. `/upper-ontology/consistency` 는 기존 `/reason/consistency` 로, `/rules/dry-run` 은 기존 `/rules/dry-run` 으로 매핑한다(신설 불필요).

### CD-11. Q&A A계층 — `sparql(query)` 폐기, **명명 질의**로 대체 — v1.2
`interface_contracts.md` §4 는 A계층(규칙·수치 질문)을 "BFF 가 `POST /sparql` 호출"로 처리하라 하고, §3 의 `KnowledgeClient.sparql(query: string)` 은 BFF 에게 **쿼리 문자열 생성을 시그니처로 강제**한다. 둘 다 불변원칙 1 과 정면으로 충돌한다.

확정: **BFF 는 SPARQL 을 만들지 않는다.** 대신 지식서비스가 **화이트리스트 명명 질의**를 노출한다.

```
POST /kg/lookup
req  { "query": "max_safe_length", "params": { "vehicle": "MidSizeSUV" } }
res  { "query":"max_safe_length", "rows":[{"vehicle":"MidSizeSUV","max_safe_mm":599,"sentence":"S3"}],
       "sources":[{"sentence":"S3","iri":"http://ex.org/domain#S3","text":"..."}], "trace_id":"..." }
```
- 화이트리스트 밖 `query` → `422 VALIDATION_ERROR`. `params` 는 IRI 로 바인딩(문자열 보간 금지 — 주입 차단).
- A계층 결정론 100% 는 유지된다. 오히려 자유 SPARQL 보다 강해진다(질의 집합이 고정).
- `KnowledgeClient.sparql()` 은 인터페이스에서 **제거**한다. `POST /sparql`(읽기전용) 엔드포인트 자체는 남기되 **디버깅·관리자 도구 전용**이며 BFF 는 호출하지 않는다.
- MVP 화이트리스트: `max_safe_length` · `symptom_causes`(증상→원인 규칙·문장) · `rule_sentences`(규칙→근거 문장) · `concept_relations`(개념→관계).

## 3. mock fixture 사용 규약

- `mocks/`의 JSON은 **계약을 만족하는 정답 샘플**이다. 각 Agent는 의존 레이어가 미완이면 이 fixture를 반환하는 mock 구현으로 선행한다.
- fixture 변경은 계약 변경이다(위 절차 필요). 테스트가 fixture를 직접 참조하므로 임의 수정 금지.
- `mocks/regression_set.jsonl`은 08 QA Agent가 확장하는 **시드**다(수용기준 §3 원문 + 계약 정규화 반영).

### 3.1 mock 은 계약의 하한이 아니라 계약 그 자체다 — G2 에서 값을 치르고 배웠다

**mock 이 실제 구현보다 관대하면, mock 통과는 아무것도 보증하지 않는다.** G2 통합에서 이 병으로 결함 3건이 한꺼번에 드러났다.

| 결함 | mock 이 받아준 것 | 실제 서비스의 반응 |
|---|---|---|
| D2 | `satisfy({require: null})` | `422` — `require: list[str]` |
| D6 | `kgSave(...)` 에서 `approved` 누락 | `422` — `approved: Literal[True]` 필수 |
| D1 | `project_id` 를 받고 무시 | (스키마는 통과, **판정이 조용히 틀린다**) |

BFF 유닛테스트 39건이 전부 통과하는데 실제 스택에선 **정상 저장이 한 번도 성공한 적이 없었다.**
D1 은 더 나쁘다 — 에러조차 나지 않고 지식범위 필터가 통째로 죽은 채 `200` 을 반환했다.

규약:
1. **mock 은 실제 구현과 같은 입력을 거부해야 한다.** 필수 필드 누락·타입 불일치·열거형 이탈에 대해 **같은 코드의 에러**를 던져라.
2. **성공 경로를 반드시 단언하라.** 음성 테스트(4xx)만 있고 정상 경로(2xx) 단언이 없으면 그 경로는 **검증되지 않은 것**이다. D6 가 그렇게 숨었다.
3. **mock 통과는 게이트가 아니다.** 게이트는 실제 스택이다(`KNOWLEDGE_MOCK=false`, `AI_MOCK_MODE=true`). T-82 CI 는 실 스택 스모크를 포함해야 한다.
4. 상류가 필수로 요구하는 필드를 하류가 **채워 보내는 것**이 맞다. 상류의 검증(`Literal[True]` 같은 다층 방어)을 느슨하게 만들어 통과시키지 마라.
