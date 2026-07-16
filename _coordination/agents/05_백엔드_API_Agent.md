# 05 · 백엔드·API Agent

## 역할
**BFF(Node/Express)** 로 외부 표면 `/api/v1` 을 노출하고, AI Gateway·SSE·지식서비스 오케스트레이션을 담당한다.
지식서비스(Python)의 라우팅 표면(`main.py`·`schemas/`)도 함께 맡는다.

## 담당 경로
`bff/src/` (`routes/`·`services/ai/`·`services/knowledgeClient.ts`·`core/`·`schemas/`), `knowledge/main.py`·`knowledge/schemas/`.

## 입력 / 계약
`contracts/api_standard.md`(외부 표면), `contracts/interface_contracts.md` §1·§3·§4(내부 계약·`AIProvider`·`KnowledgeClient`·Q&A 라우팅), `contracts/error_model.md`.

## 작업
1. **외부 엔드포인트**(`api_standard.md` §2): `/extraction/{stream(SSE),validate,save}` · `/satisfy` · `/qa` · `/graph` · `/projects*` · `/categories` · `/dashboard` · `/health` · 관리자 `/upper-ontology/*`·`/rules/*`·`/governance/concepts*`(CD-5 역할 게이트 `X-Role`, 아니면 `403`).
2. **AI Gateway**(Strategy: Mock|Claude|Gemini|Solar) — 키 없으면 자동 mock 폴백. 태스크별 기본 provider(`AI_AUTHORING_PROVIDER`·`AI_QA_PROVIDER`). 호출은 **Timeout + Retry + CircuitBreaker** 로 감싼다(NFR ≥2개).
3. **`KnowledgeClient`** — 지식서비스 접근의 **유일한 경로**. `sparql(query)` 는 **존재하지 않는다**(CD-11) — A계층은 명명 질의 `kgLookup`.
4. **Q&A 라우팅**(§4): A 명명 질의(결정론 100%) · B `satisfy`(결정론 100%) · C `rag/search` → `verified` hit만 → `answer`.
5. **satisfy 응답 무변형 통과** — 이 계약을 깨면 CD-1 정규화가 두 곳에 생긴다. 판정 필드를 BFF 가 재해석하지 않는다.
6. 에러 핸들러: `error_model.md` 대로 통일(내부 원인은 로그에만, 본문엔 `user_message`+`trace_id`). `X-Trace-Id` 전파(CD-6).
7. 멱등(`/extraction/save` 의 `draft_id`) — 스토어 영속 기준(06 과 협업). HITL: `approved:true` 없이는 저장하지 않는다.

## DoD
- 계약 스키마 검증 통과, SSE 스트리밍 동작, 에러 통일, `/health` 그린, **실 스택**(`KNOWLEDGE_MOCK=false`)에서 정상 저장·판정 성공.

## 인터페이스
- in: 지식서비스 내부 API(04·06·03). out: `/api/v1`(07 프론트·08 QA 소비). 의존: G1 이후(Phase 2).

## BFF 는 RDF 를 모른다 (불변원칙 1) ★
SPARQL·SHACL·TTL 문자열을 만들지도 파싱하지도 않는다. 조회·관리자 표면이 필요하면 **내부 엔드포인트를 신설**한다(CD-10) — BFF 가 쿼리를 조립하는 순간 원칙이 깨진다.

## 근거가 없으면 답하지 않는다 — 답을 *만들어내지* 않는다 (CD-13·CD-14) ★
실키 검증에서 값을 치르고 배웠다. mock 분류기가 가리고 있었다.

1. **접지는 라우팅보다 먼저.** `/qa` 진입 직후 `gateway.extract` → `/validate/shacl` 로 접지 판정. 알려진 개념이 0 이면 **계층과 무관하게** `insufficient_evidence:true`·`sources:[]`·"명세 근거 없음". 가드레일 뒤에 라우팅을 두면 **라우팅이 우회로가 된다**.
2. **각 계층은 fail-closed — 입력을 지어내지 마라.** A: 화이트리스트 미매칭 시 폴백 금지(기본 질의 금지). B: `parseDesign` 이 `material`·`vehicle` 을 날조하지 않는다 → 못 얻으면 CD-8 판정 보류. C: 질문의 개념이 **전부** 알려진 개념이어야 근거를 붙인다.
3. **호출을 이름으로 분리한다.** `answer(question, sources)` 는 **`sources` 가 비면 throw**(검증 답변 전용). `llmOnlyAnswer(question)` 은 환각비교의 `llm_answer` 전용. 같은 함수를 두 목적에 쓰면 근거가 비는 순간 **미검증 LLM 답변에 `determinism:"satisfy"` 라벨이 붙는다** — 실제로 그렇게 나갔다.
4. `sources` 는 `insufficient_evidence:true` 일 때 **반드시 빈 배열**이다.

> 가드레일이 LLM 의 선의에 의존하면 안 된다. Claude 는 답변 문장에서 스스로 물러섰지만 **계약 필드는 거짓말을 했다**.

## 개발 환경
BFF·프론트는 **Node 20+**(venv 무관). 지식서비스 쪽(`main.py`·`schemas/`) Python 작업만 `knowledge/.venv`(3.12) 또는 Docker. 상세: `공유표준/개발환경.md`.

## Solar(Upstage) provider 참고
`공유표준/참고_solar_upstage.md`. OpenAI 호환 SDK + base_url + `Studio_API_Key`(호스트 env). **키 하드코딩·커밋 금지**(불변원칙 6).
실측: `json_schema` strict 가 solar-pro3 추론을 눌러 품질이 떨어져 **`json_object` + 프롬프트 스키마**를 쓴다.
