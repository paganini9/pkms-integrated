# 계약 · 인터페이스 (BFF↔지식서비스 · 레이어 Protocol) — v1 freeze

> 레이어 간 **타입 시그니처**를 고정해 병렬·모의(mock) 개발을 가능케 한다.
> 근거: `docs/기술_설계_명세서.md` §1·§3·§5·§6. 외부 API는 `api_standard.md`.

## 0. 경계

```
frontend ──/api/v1──▶ bff (Node)  ──HTTP(내부)──▶ knowledge (Python, FastAPI)
                       │                              ├ store/     Oxigraph
                       ├ aiGateway (LLM 생성 전용)     ├ reasoning/ owlready2·HermiT·pySHACL·satisfy·rule compiler
                       ├ sse                           └ rag/       Chroma · 임베딩
                       └ knowledgeClient
```
- **BFF는 RDF를 모른다.** SPARQL·SHACL·TTL 문자열을 만들지도 파싱하지도 않는다.
- **지식서비스는 LLM을 호출하지 않는다.** 자연어 생성(추출 초안·RB 파싱·답변 문장)은 전부 BFF `aiGateway`.
- 지식서비스는 `KNOWLEDGE_URL`(기본 `http://localhost:8000`, compose에서 `http://knowledge:8000`)로만 접근. 외부 포트 미공개.

## 1. 지식서비스 내부 HTTP API (Python, 05·04·03·06 합의)

버전 prefix 없음(내부). 모든 응답에 `trace_id`. 요청 헤더 `X-Trace-Id` 전파.

| 메서드 | 경로 | 담당 Agent | 설명 |
|---|---|:--:|---|
| GET | `/health` | 05 | `{status, store, reasoner, rag}` |
| POST | `/validate/shacl` | 04 | 추출결과 명세검증 (range·disjoint·SHACL) |
| POST | `/reason/consistency` | 04 | OWL 일관성·disjoint 검사 (HermiT, 없으면 owlrl 폴백) |
| POST | `/reason/classify` | 04 | 개체의 추론된 타입 사슬 |
| POST | `/satisfy` | 04 | satisfy 3단계 판정 |
| POST | `/rules/compile` | 04 | 문장→규칙→SHACL 파생 (카테고리 필터) |
| POST | `/rules/dry-run` | 04 | 규칙 변경 시뮬레이션 |
| POST | `/sparql` | 06 | **읽기 전용** SELECT/ASK/CONSTRUCT |
| POST | `/kg/save` | 06 | 트리플 + 벡터 원자적 upsert |
| POST | `/kg/delete` | 06 | 트리플 + 벡터 원자적 삭제 |
| POST | `/rag/search` | 03 | 하이브리드 검색 + 충분성 판단 |
| POST | `/rag/upsert` | 03 | 임베딩 upsert |
| GET/POST/PUT | `/projects*` | 06 | 프로젝트·요구·지식범위 CRUD |

### 1.1 요청/응답 (핵심 4개)

**`POST /validate/shacl`**
```json
req  { "concepts": [{"label":"경도","type":"Attribute"}], "relations": [{"subject":"경도","predicate":"causes","object":"겨울철"}], "project_id": null }
res  { "conforms": false,
       "violations": [{ "code":"causes_range","severity":"violation","offender":"겨울철",
                        "offender_iri":"http://ex.org/domain#Winter",
                        "message":"causes의 range는 Symptom이어야 하는데 '겨울철'은 EnvCondition입니다.",
                        "source_shape":"CausesRangeShape" }],
       "trace_id":"..." }
```

**`POST /satisfy`**
```json
req  { "design": {"material":"Rubber","length_mm":600,"spring_n":8,"arm_shape":"simple","vehicle":"MidSizeSUV","env":"Winter"},
       "require": ["RB_Winter","RB_NoChatter"],
       "categories": ["소음","떨림"] }        // CD-4: 컴파일 시점 필터. null이면 전체
res  → api_standard.md §4.4 응답과 동일 스키마 (BFF는 그대로 통과)
```
> BFF는 satisfy 응답을 **변형 없이 통과**시킨다. 이 계약을 깨면 CD-1 정규화가 두 곳에 생긴다.

**`POST /kg/save`**
```json
req  { "sentence_text":"...", "concepts":[...], "relations":[...], "category":"소음", "project_id": null }
res  201 { "sentence": {...}, "derived": {"rule":{...},"shapes":[...],"causal_edges":[...]}, "human_view": [...], "trace_id":"..." }
```
원자성: 트리플 커밋 → 벡터 upsert. 벡터 실패 시 트리플 롤백 후 `STORE_ERROR`(수용기준 §4 "트리플/벡터 불일치").

**`POST /rag/search`**
```json
req  { "query":"겨울에 고무 쓰면?", "k":6, "project_id":"uuid|null" }
res  { "hits":[{"iri":"http://ex.org/domain#S1","sentence":"S1","text":"...","score":0.82,
                "about_symptom":"Noise","derives_rule":"NoiseRule","verified":true}],
       "sufficient": true, "trace_id":"..." }
```
- `verified` (**CD-9**): 그 문장의 규칙이 **프로젝트 지식범위로 컴파일된 규칙 집합**에 속하는가. `mitigate` 규칙(게이트 없음)도 포함된다 — AC-2 의 근거 S2·S5 가 mitigate 다. 미검증 = 알 수 없는 규칙 · 지식범위 밖(CD-4) · 컴파일 실패.
- **`verified:false`인 hit는 답변 근거로 쓰지 않는다**(루브릭 "RAG 충분성: 미검증 근거 0").
- `sufficient`: `verified:true` hit가 1건 이상.

## 2. 레이어 Protocol — Python (`knowledge/`)

각 Protocol마다 `*_mock` 구현을 함께 제공한다(fixture 반환). Phase 1에서 서로 대기하지 않기 위한 필수 장치.

```python
# store/ — 06 퍼시스턴스
class Store(Protocol):
    def query(self, sparql: str, *, readonly: bool = True) -> list[dict]: ...
    def save_sentence(self, sentence: SentenceIn) -> SavedSentence: ...   # 트리플 커밋(벡터는 호출자가 조율)
    def delete(self, iri: str) -> None: ...
    def subgraph(self, iris: list[str], depth: int = 2) -> "Graph": ...   # reasoner 입력용 rdflib Graph
    def load_seed(self, ttl_paths: list[str]) -> int: ...                 # 기동 시 m0/m1/shapes/rules 적재(멱등)

# reasoning/ — 04 그래프·코어
class Reasoner(Protocol):
    def consistency(self, graph: "Graph") -> ConsistencyResult: ...       # HermiT, 미가용 시 owlrl 폴백
    def classify(self, iri: str) -> list[str]: ...                        # 추론된 타입 사슬
    def validate_shacl(self, data: "Graph", shapes: "Graph") -> ShaclReport: ...

class RuleCompiler(Protocol):
    """문장 → 구조화 DesignRule → SHACL·인과엣지·사람뷰. 단일 진실원은 rules.ttl."""
    def compile(self, categories: set[str] | None = None) -> CompiledRules: ...  # gen_shacl.compile_rules 이식
    def derive_from_sentence(self, sentence: SentenceIn, structured: DesignRuleIn) -> CompiledRules: ...

class SatisfyEngine(Protocol):
    def satisfy(self, design: Design, require: list[str], categories: set[str] | None) -> SatisfyResult: ...
    # (1) qualitative subsumption → (2) SHACL 게이트 + 구간 비교기 → (3) 무증상 규칙
    # 시그니처 캐시 키: sha256(design_canonical + sorted(require) + sorted(categories) + shapes_hash)

# rag/ — 03 RAG·지식
class Embedder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...   # 다국어 ST, EMBEDDING_MODE=mock이면 해시 기반 결정론 벡터

class Retriever(Protocol):
    def search(self, query: str, k: int = 6, project_id: str | None = None) -> list[Hit]: ...
    def is_sufficient(self, hits: list[Hit]) -> bool: ...          # verified=True hit ≥ 1
    def upsert(self, items: list[VectorItem]) -> int: ...
    def delete(self, iris: list[str]) -> int: ...
```

**소유 경로** (병렬 안전 — 남의 경로 수정 금지)
| Agent | 경로 |
|---|---|
| 02 데이터 | `knowledge/ontology/` (시드 TTL·정규화 스크립트) |
| 03 RAG | `knowledge/rag/` |
| 04 그래프·코어 | `knowledge/reasoning/` |
| 06 퍼시스턴스 | `knowledge/store/` |
| 05 백엔드 | `knowledge/main.py`·`knowledge/schemas/`·`bff/src/` |
| 07 프론트 | `frontend/src/` |
| 08 QA | `tests/` |
| 09 DevOps | `docker-compose.yml`·`*/Dockerfile` |

공유 파일(`knowledge/main.py`의 router include, `docker-compose.yml`, `contracts/`) 변경은 **오케스트레이터 경유**.

## 3. 레이어 Protocol — Node (`bff/`)

```ts
// services/ai — AI Gateway (Strategy: Mock | Claude | Gemini)
interface AIProvider {
  name: "mock" | "claude" | "gemini";
  extract(text: string): AsyncIterable<ExtractionEvent>;   // structured output, temperature 0~0.2
  parseRequirements(text: string): Promise<RequirementDraft[]>;
  answer(question: string, context: Source[]): Promise<string>;  // temperature 중간
}
// 키 없으면 자동 mock. 호출은 Timeout + Retry + CircuitBreaker 로 감싼다(NFR 신뢰성, 2개↑).

// services/knowledgeClient — 지식서비스 클라이언트 (유일한 지식 접근 경로)
interface KnowledgeClient {
  health(): Promise<HealthResult>;
  validateShacl(req: ValidateReq): Promise<ValidateRes>;
  satisfy(req: SatisfyReq): Promise<SatisfyRes>;      // 응답 무변형 통과
  kgSave(req: SaveReq): Promise<SaveRes>;
  sparql(query: string): Promise<Row[]>;
  ragSearch(req: SearchReq): Promise<SearchRes>;
  rulesCompile(categories?: string[]): Promise<CompiledRules>;
  rulesDryRun(req: DryRunReq): Promise<DryRunRes>;
}
```

**추출 Structured Output 스키마** (LLM 강제 출력 — 기술설계 §4):
```json
{ "concepts":  [{"label":"소음","type":"Symptom"}],
  "relations": [{"subject":"고무","predicate":"causes","object":"소음","evidence":"S1"}] }
```
`type`·`predicate`는 `api_standard.md` §3 열거형을 벗어날 수 없다. 벗어나면 `unknown_concept` 위반으로 검증 단계에서 걸린다(할루시네이션 방지).

## 4. Q&A 라우팅 계약 (BFF)

| layer | 판정 기준 | 처리 | 결정론 |
|:--:|---|---|:--:|
| A | 규칙·수치 질문 ("안전 길이는?") | 지식서비스 `POST /sparql` | 100% |
| B | 설계 검증 질문 ("고무 600mm 써도 될까?") | `POST /satisfy` | 100% |
| C | 자유 질의 | `POST /rag/search` → `verified` hit만 → `aiGateway.answer` | 근거만 결정론 |

- 분류는 BFF에서 LLM structured output(`{"layer":"A|B|C"}`, temperature 0) + 규칙 기반 폴백(키워드).
- 어떤 layer든 `mode:"compare"`이면 `aiGateway.answer(question, [])`(무근거 LLM 단독)를 **병렬 호출**해 `llm_answer`에 싣고 대조기가 `comparison`을 계산한다.

## 5. 모의(mock) 규약

- 각 Protocol마다 `*_mock` 구현이 `contracts/mocks/*.json`을 그대로 반환한다.
- 04는 store/rag mock으로 satisfy 완주 가능해야 한다(임계 경로 보호).
- 07은 05 미완 시 `contracts/mocks/`를 서빙하는 mock API(`vite` 프록시 or `msw`)로 선행한다.
- fixture는 재현성 자산이다 — 테스트가 직접 참조하므로 임의 변경 금지(계약 변경 절차 필요).

## 6. 신뢰성 패턴 (최소 2개 구현 — NFR)

| 패턴 | 적용 지점 | 기본값 |
|---|---|---|
| Timeout | LLM 호출 · 지식서비스 호출 | LLM 30s · knowledge 20s (satisfy 60s) |
| Retry | LLM 5xx·타임아웃 | 지수 백오프 2회, 4xx는 재시도 금지 |
| Circuit Breaker | LLM provider | 연속 5회 실패 → 60s open → **Mock 폴백** |
| Idempotency | `/extraction/save` | `draft_id` 기준 중복 저장 방지 |

reasoner 지연은 **시그니처 캐시**로 흡수한다(미스 시 프론트에 진행 표시).
