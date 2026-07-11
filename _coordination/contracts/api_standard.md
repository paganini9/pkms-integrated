# 계약 · API 표준 — BFF 외부 API (`/api/v1`) · v1 freeze

> 05 백엔드가 구현, 07 프론트가 소비, 08 QA가 검증한다. 근거: `docs/기술_설계_명세서.md` §6·§7.
> **이 문서에 없는 외부 표면은 존재하지 않는다.** 지식서비스(Python)는 외부 노출 금지 → `interface_contracts.md`.

## 1. 공통 규약

- Base path: **`/api/v1`**. 본문은 JSON(UTF-8). 시각은 ISO-8601 UTC.
- 요청 검증: BFF는 형식(zod), 지식서비스는 Pydantic으로 이중 검증. 위반 시 `422 VALIDATION_ERROR`.
- 모든 응답 본문(에러 포함)에 `trace_id: string`.
- 헤더
  | 헤더 | 방향 | 의미 |
  |---|---|---|
  | `X-Role: engineer\|admin` | in | Mock-Role 인증 (CD-5). 없으면 `engineer` |
  | `X-Thread-Id: <uuid>` | in/out | 대화 세션. 없으면 BFF 생성 후 응답에 반환 |
  | `X-Trace-Id: <uuid>` | in/out | 관측성. 없으면 BFF 생성 (CD-6) |
- 상태 판정 필드(`satisfies`·`conforms`·`violations`)는 **지식서비스 결정론 결과 그대로** 전달한다. BFF가 재해석·보정하지 않는다.

## 2. 엔드포인트 목록

| 메서드 | 경로 | FR | 역할 |
|---|---|:--:|:--:|
| POST | `/api/v1/extraction/stream` (SSE) | FR-01 | engineer |
| POST | `/api/v1/extraction/validate` | FR-02 | engineer |
| POST | `/api/v1/extraction/save` | FR-03·3d | engineer |
| POST | `/api/v1/satisfy` | FR-04·05 | engineer |
| POST | `/api/v1/qa` | FR-06~09 | engineer |
| GET | `/api/v1/graph` | FR-10 | engineer |
| POST | `/api/v1/projects` · GET `/api/v1/projects/{id}` | FR-3b | engineer |
| PUT | `/api/v1/projects/{id}/knowledge-scope` | FR-3c | engineer |
| POST | `/api/v1/projects/{id}/requirements` | FR-3b | engineer |
| GET | `/api/v1/categories` | FR-3c | engineer |
| GET | `/api/v1/dashboard` | FR-16 | engineer |
| GET/POST | `/api/v1/upper-ontology/*` | FR-12 | **admin** |
| GET/POST | `/api/v1/rules/*` | FR-13 | **admin** |
| GET/POST/DELETE | `/api/v1/governance/concepts*` | FR-14 | **admin** |
| GET | `/api/v1/health` | FR-15 | — |

## 3. 공통 타입

```ts
type ConceptType = "PartType"|"Component"|"Material"|"VehicleType"|"EnvCondition"|"Symptom"|"Behavior"|"Attribute";
type Predicate   = "causes"|"mitigates"|"aggravates"|"conditionedOn"|"hasMaterial"|"has_part"|"mountedOn"|"operatesIn";
type Polarity    = "cause"|"mitigate"|"aggravate";

interface Concept  { label: string; type: ConceptType; iri?: string; span?: [number, number]; }
interface Relation { subject: string; predicate: Predicate; object: string; evidence?: string; confidence?: number; }

interface Violation {           // 명세검증·SHACL 위반의 단일 표현
  code: "causes_range"|"disjoint"|"shacl_constraint"|"missing_required"|"unknown_concept";
  severity: "violation"|"warning";     // CD-7 참조. violation = amber + 저장 차단 / warning = 정보 + 저장 허용
  offender: string;                    // 위반 대상 라벨 (예: "겨울철")
  offender_iri?: string;
  message: string;                     // 한글 설명 (사용자에게 그대로 노출)
  sentence?: string;                   // 근거 문장 코드 "S1" | "S3,S5"
  source_shape?: string;               // 예: "ChatterShape"
}

interface Source { sentence?: string; rule?: string; iri: string; text?: string; }
```

`Design` — satisfy·설계 입력의 단일 표현:
```ts
interface Design {
  id?: string;               // 저장된 설계면 "Blade_bad"
  label?: string;
  material: "Rubber"|"Silicone";          // 필수
  vehicle: "MidSizeSUV"|"CompactSedan";   // 필수
  length_mm?: number | null;   // >0, CD-8: 선택
  spring_n?: number | null;    // >0, CD-8: 선택
  arm_shape?: "simple"|"complex" | null;
  env?: "Winter" | null;
}
```
> **CD-8** — 수치·형상은 선택이다. 누락 시 `422 VALIDATION_ERROR`가 아니라 **SHACL 경고 + 판정 보류**로 응답한다(수용기준 §4). → `200`, `satisfies: null`, `pending_reason: "missing_required"`, 경고는 `steps[1].warnings[]`.
> 필수로 두면 결측 요청이 스키마 검증에서 걸려 판정 보류 경로에 도달할 수 없다.

## 4. 엔드포인트 상세

### 4.1 `POST /api/v1/extraction/stream` — SSE (FR-01)
요청:
```json
{ "text": "겨울철 저온에서 고무 블레이드는 소음이 발생한다", "thread_id": "uuid?", "project_id": "uuid?" }
```
`text`: 1..2000자.

응답 `text/event-stream`. **이벤트 순서**: `status*` → (`concept`|`relation`)* → `validation` → `done`. `error`는 어디서든 종료.
```
event: status      data: {"stage":"extract|validate","msg":"개념 추출 중"}
event: concept     data: {"label":"겨울철","type":"EnvCondition","span":[0,3]}
event: relation    data: {"subject":"고무","predicate":"causes","object":"소음","evidence":"입력문장"}
event: validation  data: {"conforms":false,"violations":[Violation, ...]}
event: done        data: {"thread_id":"...","draft_id":"...","trace_id":"..."}
event: error       data: {"code":"LLM_ERROR","user_message":"...","trace_id":"..."}
```
- 부분 결과 허용: `done` 전 `error` 시 프론트는 그때까지 렌더를 유지하고 안내를 띄운다.
- `validation` 이벤트는 BFF가 지식서비스 `POST /validate/shacl`을 호출한 결과다(LLM 아님).

### 4.2 `POST /api/v1/extraction/validate` (FR-02)
요청 `{ "concepts": Concept[], "relations": Relation[], "project_id"?: string }`
응답 `200 { "conforms": boolean, "violations": Violation[], "trace_id": string }`

### 4.3 `POST /api/v1/extraction/save` — HITL 게이트 (FR-03·FR-3d)
요청:
```json
{ "sentence_text": "겨울철 저온에서 고무는 경도가 상승해 소음을 유발한다.",
  "concepts": [...], "relations": [...], "category": "소음",
  "approved": true, "project_id": "uuid?", "draft_id": "uuid?" }
```
`draft_id` 는 `/extraction/stream` 의 `done` 이벤트가 준 값이다. 멱등 키로 쓰여 중복 저장을 막는다(§6 Idempotency). v1.3 에 문서화(07 보고 — fixture 에는 있었으나 이 예시에 빠져 있었다).
응답 `201`:
```json
{ "sentence": { "id": "S7", "iri": "http://ex.org/domain#S7", "text": "...", "category": "소음",
                "mentions": ["Winter","Rubber","Noise"], "about_symptom": "Noise", "polarity": "cause" },
  "derived": {
    "rule":   { "id": "NoiseRule", "label": "겨울 + 고무 → 소음", "polarity": "cause", "category": "소음",
                "conds": [{"path":"hasMaterial","op":"eq","val":"Rubber"},{"path":"operatesIn","op":"eq","val":"Winter"}] },
    "shapes": [{ "id": "NoiseShape", "gate_for": "Noise", "sentence": "S1" }],
    "causal_edges": [{ "subject": "NoiseRule", "predicate": "causes", "object": "Noise" }]
  },
  "human_view": ["겨울 + 고무 → 소음  [cause·S1·소음] → Noise"],
  "trace_id": "..." }
```
- `approved !== true` 또는 `severity:"violation"`이 하나라도 있으면 **저장 차단** → `409 GUARDRAIL_BLOCKED`.
- 엔지니어는 `sentence`와 `derived`(읽기 전용 요약)만 본다. **규칙·SHACL 직접 편집 표면은 존재하지 않는다** — 편집은 문장 수정 → 재파생.
- 트리플 저장과 벡터 upsert는 **원자적**. 한쪽 실패 시 롤백하고 `500 STORE_ERROR`.

### 4.4 `POST /api/v1/satisfy` (FR-04·05) ★
요청:
```json
{ "project_id": "uuid",
  "design": { "material":"Rubber","length_mm":600,"spring_n":8,"arm_shape":"simple","vehicle":"MidSizeSUV","env":"Winter" },
  "require": ["RB_Winter","RB_NoChatter"] }
```
- `require` 생략 시 프로젝트의 `hasRequirement` 전체.
- 적용 규칙은 **프로젝트가 선택한 지식 카테고리로 컴파일된 게이트만** (CD-4).

응답 `200`:
```json
{ "satisfies": false,
  "pending_reason": null,
  "applied_categories": ["소음","떨림"],
  "steps": [
    { "stage":"subsumption",    "ok": false, "detail": "재질 고무 ∧ 겨울 → 소음(S1)" },
    { "stage":"shacl_interval", "ok": false,
      "checks": [ {"name":"길이 구간포함 length ≤ maxSafe","expr":"600 ≤ 599","ok":false},
                  {"name":"스프링 임계 springN ≥ 10","expr":"8 ≥ 10","ok":false} ] },
    { "stage":"symptom_free",   "ok": false,
      "exhibited": [ {"symptom":"Noise","label":"소음","sentences":["S1"]},
                     {"symptom":"TipChatter","label":"끝단 떨림","sentences":["S3,S5","S4","S6"]} ] }
  ],
  "violations": ["S1","S3","S4","S6"],
  "violation_bases": ["S1","S3,S5","S4","S6"],
  "violated_requirements": [
    { "rb":"RB_Winter",    "label":"겨울 저소음(소음 없음)", "forbids":"Noise",      "sentences":["S1"] },
    { "rb":"RB_NoChatter", "label":"끝단 떨림 없음",         "forbids":"TipChatter", "sentences":["S3,S5","S4","S6"] }
  ],
  "alternatives": ["재질→실리콘(S2)","길이→차종 안전길이 이내(S5)","스프링→≥10N","암형상→complex"],
  "justification": ["(1) 정성 subsumption ✘ — 재질 고무 ∧ 겨울 → 소음(S1)", "..."],
  "cache_hit": false,
  "trace_id": "..." }
```
- `violations` / `violation_bases` 정규화는 **CD-1**. `justification`은 감사 로그로도 보존(NFR 관측성).
- 3단계는 항상 `steps`에 순서대로 실린다: `subsumption` → `shacl_interval` → `symptom_free`.
- 수치 누락 시: `satisfies: null`, `pending_reason: "missing_required"`, `violations: []`, SHACL 경고를 **`steps[1].warnings[]`** 에 실어 반환(200).
  `checks` 는 실제로 비교한 구간 검사만 담는다(판정 못 한 항목은 `checks` 가 아니라 `warnings`). v1.3 정정 — 본 문서 §3 CD-8 과 이 줄이 서로 달랐다(07 보고, fixture `satisfy_pending_missing.json` 이 정본).

### 4.5 `POST /api/v1/qa` (FR-06~09)
요청 `{ "question": "중형 SUV에 고무 600mm 써도 될까?", "mode": "compare"|"verified", "project_id"?: string, "thread_id"?: string }`

응답 `200`:
```json
{ "layer": "B",
  "verified_answer": {
    "text": "불가합니다. 중형 SUV 안전길이 599mm를 초과해 끝단 떨림, 겨울철 고무는 소음이 발생합니다.",
    "determinism": "sparql|satisfy|rag",
    "sources": [ {"sentence":"S3","iri":"http://ex.org/domain#S3","text":"중형 SUV에서 ..."},
                 {"rule":"ChatterRule","iri":"http://ex.org/domain#ChatterRule"} ] },
  "llm_answer": { "text": "네, 가능합니다.", "model": "mock" },
  "comparison": { "mismatches": [{"claim":"가능","verdict":"위반","evidence":["S3","S1"]}],
                  "violation_rate": 1.0, "agreement_rate": 0.0 },
  "insufficient_evidence": false,
  "trace_id": "..." }
```
- `layer`: `A`(규칙질문→SPARQL) · `B`(설계검증→satisfy/SHACL) · `C`(자유질의→RAG).
- **C 계층 충분성**: RAG 검색 문장 중 **규칙 검증을 통과한 것만** `sources`에 실린다. 통과분이 없으면 `insufficient_evidence: true`이고 `verified_answer.text`는 "명세 근거 없음"을 명시한다(억지 답 금지).
- `mode: "verified"`면 `llm_answer`·`comparison`은 `null`.

### 4.6 `GET /api/v1/graph` (FR-10)
쿼리: `?layer=M0|M1|M2&symptom=TipChatter&sentence=S3&project_id=uuid&limit=500`
```json
{ "nodes": [{ "id":"S3","label":"중형 SUV에서 ...","kind":"sentence","layer":"M1","iri":"...","inferred":false }],
  "edges": [{ "source":"ChatterRule","target":"TipChatter","predicate":"causes","inferred":false,"evidence":"S3,S5" }],
  "stats": { "nodes": 24, "edges": 31, "inferred_edges": 3 },
  "trace_id": "..." }
```
`kind` ∈ `concept|sentence|rule|symptom|design|requirement|class`. `inferred: true`는 프론트에서 **점선**으로 렌더한다(AC-4).

### 4.7 프로젝트 (FR-3b·3c)
```
POST /api/v1/projects
  req { "name":"겨울용 SUV 와이퍼", "target_vehicle":"MidSizeSUV", "target_env":"Winter", "knowledge_categories":["소음","떨림"] }
  res 201 { "id":"uuid", "iri":"http://ex.org/eng#Proj_WinterSUV", ... }

GET /api/v1/projects/{id}
  res 200 { id, name, target_vehicle, target_env, knowledge_categories[], requirements[], designs[] }

PUT /api/v1/projects/{id}/knowledge-scope
  req { "categories": ["떨림"] }              # 미선택 카테고리 규칙은 satisfy에서 제외 (AC-scope)
  res 200 { "categories":["떨림"], "compiled_gates": 3 }

POST /api/v1/projects/{id}/requirements    # 자연어 → RB 파싱 (LLM 생성 + 검증)
  req { "text": "겨울철에도 소음이 없고 중형 SUV에서 떨림이 없어야 한다" }
  res 201 { "requirements": [ {"id":"RB_Winter","label":"겨울 저소음(소음 없음)","forbids_symptom":"Noise"},
                              {"id":"RB_NoChatter","label":"끝단 떨림 없음","forbids_symptom":"TipChatter"} ],
            "unknown_symptoms": [] }
```
- `unknown_symptoms`가 비지 않으면 프론트는 "지식 추가" 유도를 띄운다(AC-1P). 저장은 알려진 증상분만.

`GET /api/v1/categories` → `{ "categories": [{"name":"소음","sentences":2,"rules":2}, {"name":"떨림","sentences":4,"rules":3}] }`

### 4.8 관리자 표면 (admin 전용, 비관리자 `403 FORBIDDEN`)
```
GET  /api/v1/upper-ontology/classes                → 클래스·관계 트리
POST /api/v1/upper-ontology/classes                → 편집(approved:true 필요)
POST /api/v1/upper-ontology/consistency            → { consistent, clashes[], dl_axioms[] }   (HermiT)
POST /api/v1/upper-ontology/impact                 → { affected_m1: [...], affected_m2: [...] }  (AC-6)

GET  /api/v1/rules                                 → 생성 뷰 { rules[], shapes[], human_view[] } (읽기 전용)
POST /api/v1/rules/dry-run                         → { new_violations[], affected_instances[] }  (AC-7)
GET  /api/v1/rules/{id}/impact                     → 영향 M2 인스턴스 목록

GET    /api/v1/governance/concepts                 → { builtin[], custom[] }
POST   /api/v1/governance/concepts                 → custom 생성
DELETE /api/v1/governance/concepts/{id}            → custom 삭제 200 / builtin 삭제 400 BUILTIN_LOCKED  (AC-8)
```
> `/rules`에 **PUT/PATCH(직접 편집)는 없다.** 규칙·SHACL은 문장 파생물이다(FR-3d).

### 4.9 `GET /api/v1/dashboard` (FR-16)
`{ "m0": {"classes": 18, "relations": 9}, "m1": {"sentences": 6, "rules": 5, "concepts": 12}, "m2": {"projects":1,"designs":2,"violations":4}, "recent": [...], "trace_id": "..." }`

### 4.10 `GET /api/v1/health`
```json
{ "status": "ok|degraded",
  "llm_provider": "mock|claude|gemini",
  "knowledge": { "status":"ok", "store":"ok", "reasoner":"ok|no_jre", "rag":"ok" },
  "trace_id": "..." }
```
지식서비스 도달 불가 시 `status: "degraded"`, HTTP는 200(프론트가 배너 표시).

## 5. SSE 소비 계약 (프론트)

- 순서: `status*` → (`concept`|`relation`)* → `validation` → `done`. `error`는 종료 신호.
- 재연결·재시도는 프론트가 하지 않는다(중복 추출 방지). `error` 수신 시 "다시 시도" 버튼 노출.
- 이벤트 페이로드는 항상 단일 JSON 객체 1줄.

## 6. 답변 구조 순서 (프론트 렌더 규약)

`핵심 답 → 근거(검증) → 주의 → 출처(문장·규칙)` (기술설계 §7). 환각비교에서 `llm_answer`는 시각적으로 **미검증**임이 구분되어야 한다(색·라벨).
