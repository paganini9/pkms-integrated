# 통합 로그 (오케스트레이터 소유)

체크포인트별 게이트 판정·근거·미결 사항. 판정은 **실행한 증거**로만 한다.

---

## G0 — 계약 freeze · 2026-07-10 · **통과**

### 산출물
- `_coordination/contracts/` v1: `README.md`(CD-1~7) · `api_standard.md` · `interface_contracts.md` · `error_model.md` · `schemas/*.json`(6) · `mocks/*`(15 + 회귀 시드) · `validate_contracts.py`
- 리포 골격: `frontend/`(Vite+React+TS) · `bff/`(Express+TS) · `knowledge/`(FastAPI) + core(설정·로깅·예외·trace·Protocol·mock)

### 검증 증거 (실행함)
| 검사 | 결과 |
|---|---|
| `python _coordination/contracts/validate_contracts.py` | ✅ 스키마 6개 · 검증 27건 통과 |
| 음성 테스트(스키마) — `stage:"llm_guess"` 주입 · 범주 밖 predicate · CD-1 불변식 위반 | ✅ 3건 모두 검출 (검증기가 no-op 아님) |
| Pydantic 모델 ↔ fixture 교차검증 11건 | ✅ 전건 수용 |
| 음성 테스트(모델) — `satisfies:"아마도 불만족"` · `approved:false` | ✅ 거부 (결정론 우선 · HITL 게이트) |
| `knowledge` `/health` + 에러 핸들러 | ✅ 200 · 409 GUARDRAIL_BLOCKED · **내부 원인 본문 비노출 확인** |
| `bff` typecheck · `frontend` typecheck | ✅ 0 errors |
| BFF `/api/v1/health` → 지식서비스 왕복 | ✅ `X-Trace-Id: e2e-check-001` 전파 확인 |
| 지식서비스 down → BFF health | ✅ `200 degraded` (계약대로 500 아님) |
| 참조 구현 `satisfy_demo.py` | ✅ 설계 A 4위반(S1·S3·S4·S6) / 설계 B 만족 — **AC-2 일치** |
| 참조 구현 `project_scope_demo.py` | ✅ 프로젝트 A 4게이트·4위반 / B 3게이트·3위반 — **AC-scope 일치** |

### 통합 게이트 체크리스트 (오케스트레이터 §5)
- [x] 추적성: FR-01~16 → 엔드포인트 → 회귀셋 id 연결(`mocks/regression_set.jsonl` 의 `fr`·`ac` 필드)
- [x] 계약 준수: 스키마·fixture·Pydantic·TS 타입 4중 일치
- [x] 경계: 지식서비스 내부 전용, BFF `/api/v1` 만 외부. BFF 는 RDF 를 다루지 않음(코드 리뷰로 확인)
- [x] 안전: HITL(`approved: Literal[True]`) · "명세 근거 없음" 분기 계약화
- [x] 신뢰성: Timeout/Retry/Breaker/Idempotency 4종 계약 명시(구현은 T-50)
- [x] 재현성: 추출 temp 0~0.2 · 판정은 결정론 엔진 전담 명문화
- [ ] QA: 회귀셋은 **시드**만 존재 (T-70 에서 확장·실행)
- [ ] 패키징: compose 미착수 (T-80)

> 마지막 두 항목은 G0 범위 밖이다(각각 Phase 3). G0 판정에 영향 없음.

### 계약 결정 (명세 모호함 해소)
G0 에서 명세 간 충돌 **2건**을 발견해 확정했다. 상세는 `contracts/README.md` §2.

1. **CD-1** — AC-2(`S1·S3·S4·S6`)와 회귀셋 `scope-A`(`["S1","S3,S5",…]`)가 다른 표기를 쓴다.
   → `violations`(정규화·개별문장) + `violation_bases`(게이트 원본 basis) **두 필드**로 분리. `S5`는 극성 `mitigate` 라 위반에서 제외.
   참조 구현 실행으로 두 표기가 모두 실재함을 확인했다.
2. **CD-7** — AC-1 은 range 위반을 "amber 경고", 수용기준 §4 는 같은 위반에 "저장 차단"이라 한다.
   → `severity:"violation"` = **amber + 저장 차단**(409). `warning` = 정보 + 저장 허용. amber 는 "고쳐야 저장된다"는 신호다.

그 외 확정: CD-2(문장코드↔IRI 병기) · CD-3(규칙 id 는 `rules.ttl` 기준) · CD-4(카테고리는 컴파일 시점 필터) · CD-5(Mock-Role 헤더) · CD-6(trace_id 전파).

### 환경 이슈
| 항목 | 상태 | 조치 |
|---|---|---|
| Java/JRE | **없음** | HermiT 불가 → `owlrl` 폴백(T-33), Docker 에 JRE 포함(T-80). `/health.reasoner="no_jre"` |
| `gh` CLI | 없음 | `origin` 이미 연결됨(`paganini9/pkms-integrated`). PR 은 재현님 요청 시 |
| `chromadb 0.6.3` | **설치 실패** | `chroma-hnswlib` 가 MSVC 빌드툴 요구 → **1.5.9**(Rust 백엔드)로 상향. requirements 에 사유 주석 |

### 다음
Phase 1(02·03·04·06) 병렬 착수 **승인 요청**. 임계 경로는 T-30(satisfy 코어).

---

## G1 — 인터페이스 적합성 · 2026-07-10 · **통과**

### 산출물
| Agent | 경로 | 내용 |
|---|---|---|
| 02 데이터 | `knowledge/ontology/` | CD-3 정규화 · `check_seed.py`(일관성 게이트) |
| 03 RAG | `knowledge/rag/` | 임베딩(mock/st) · Chroma · 하이브리드 검색 · 충분성 · `/categories` |
| 04 그래프·코어 | `knowledge/reasoning/` | 규칙 컴파일러 · satisfy 3단계 · 명세검증 · reasoner(owlrl 폴백) · 시그니처 캐시 · dry-run |
| 06 퍼시스턴스 | `knowledge/store/` | Oxigraph 영속 · 읽기전용 SPARQL 게이트 · 트리플+벡터 원자성 · 프로젝트 CRUD |
| 00 오케스트레이터 | `knowledge/main.py` | 라우터 결선 · 레이어 결선 · 에러 핸들러 |

### 검증 증거 (실행함)
| 검사 | 결과 |
|---|---|
| `pytest knowledge/tests/` | ✅ **61 passed** (rag 7 · store 11 · reasoning 26 · G1 통합 17) |
| `validate_contracts.py` | ✅ 27건 |
| `check_seed.py` | ✅ 6문장 · 5규칙 · 게이트 4/3 |
| `check_seed.py ontology-ref/ontology` (정규화 전) | ✅ **3건 검출** — 검증기가 no-op 아님 |
| 회귀 `sat-bad` | ✅ `violations=[S1,S3,S4,S6]` · `bases=[S1,"S3,S5",S4,S6]` |
| 회귀 `sat-good` | ✅ `satisfies=true` |
| 회귀 `scope-A`/`scope-B` | ✅ 4위반 / 3위반 (CD-4) |
| 회귀 `sat-pending` | ✅ `200 satisfies=null` (422 아님) |
| 회귀 `ext-range` | ✅ `causes_range` · `severity=violation` |
| 회귀 `rag-verified-only` | ✅ `sufficient=true` |
| BFF↔지식서비스 왕복 | ✅ `X-Trace-Id` 전파 · 지식서비스 down 시 `200 degraded` |
| bff·frontend typecheck | ✅ 0 errors |
| 판정 결정론 | ✅ 3회 반복 동일 (SHACL 리포트 순서 비의존) |

### G1 통과 조건
- [x] 02·03·04·06 산출물이 계약 스키마 검증 통과
- [x] `sat-bad`·`sat-good`·`scope-A`·`scope-B` 전건 통과
- [x] mock↔실구현 교체 가능 — `main._wire_layers()` 가 03 의 `MockRuleVerifier` 를 04 실제 컴파일러로 교체

### 이번 페이즈에서 잡은 결함 (전부 실행으로 발견)

1. **CD-8 — 판정 보류 경로가 도달 불가능했다.** `Design` 스키마가 `length_mm`·`spring_n`·`arm_shape` 를 필수로 요구했다. 그러면 수치 결측 요청이 `422` 에서 걸려, 계약이 명시한 `200 satisfies:null` 판정 보류에 **영원히 도달하지 못한다.** → `material`·`vehicle` 만 필수로 바꾸고 나머지는 nullable. (G0 에서 내가 만든 모순)

2. **CD-9 — `verified` 를 게이트 기준으로 하면 정답 근거가 사라진다.** `verified` 를 "SHACL 게이트로 컴파일되었는가"로 구현하면 `mitigate` 규칙이 전부 미검증이 된다. 그런데 AC-2 는 설계 B 만족의 근거로 **S2·S5** 를 요구하고 둘 다 `mitigate` 다. → `verified` = "프로젝트 지식범위로 컴파일된 규칙에 속하는가"(mitigate 포함).

3. **pySHACL 이 정본 shapes 그래프를 오염시켰다.** `pyshacl.validate(shacl_graph=...)` 는 넘겨받은 그래프에 트리플을 주입한다(측정: +2). 결과로 (a) `shapes_hash` 가 매 호출 달라져 **satisfy 시그니처 캐시가 영원히 빗나갔고**(단위 테스트는 통과하는데 HTTP 에서만 실패), (b) `/rules/compile` 의 `shapes_ttl` 이 호출할수록 부풀었다. → 해시는 컴파일 시점 고정, pySHACL 에는 사본 전달. 회귀 테스트 2개 추가.

4. **FastAPI 기본 에러가 계약 에러 모델을 우회했다.** 스키마 위반은 `{"detail":[...]}`, 본문 파싱 실패는 `{"detail":"..."}` 로 나갔다 — `code`·`trace_id` 없음. 05·07 이 두 가지 에러 형태를 다뤄야 했을 것이다. → `RequestValidationError`·`StarletteHTTPException` 핸들러 추가, `details.fields` 로 위반 필드 경로 노출.

5. **SHACL 리포트 순서 비결정성.** 위반 shape 를 리포트 순서대로 모으면 `alternatives`·`violation_bases` 순서가 실행마다 달라진다(NFR 재현성 위반). → 근거 문장 번호로 정렬.

### 알려진 한계 (Phase 2 이전에 인지할 것)
- **원자성은 보상 롤백**이다(06 보고). 트리플 커밋 후 벡터 upsert 실패 시 트리플을 지운다. 보상 단계 **자체가 실패**하면(크래시·디스크 오류) 불일치가 남는다. 진짜 2PC 가 아니다. 또한 `next_sentence_code` 의 max+1 발급은 다중 프로세스에서 경합 가능.
- **mock 임베딩은 표층 어휘 매칭**이다(03 보고). 동의어·의역을 못 잡는다. 절대 점수(0.0~0.35)로 임계값 컷을 하면 안 되고 순위·`verified` 만 신뢰해야 한다. 운영 품질은 `EMBEDDING_MODE=st` 필요.
- **JRE 부재** — HermiT 미가동, owlrl 폴백 중. `/health.reasoner="no_jre"`. FR-12(상위 온톨로지 일관성 검사)를 실제로 검증하려면 JRE 가 필요하다(T-80 Docker).
- 통합 테스트가 개발용 영속 스토어(`knowledge/data/`)를 공유한다. 서비스가 떠 있으면 Oxigraph 파일 락 충돌로 테스트가 깨진다(재현함). T-82 CI 에서 격리 필요.

### 다음
Phase 2(05 백엔드 API → 07 프론트) 착수 **승인 요청**. 임계 경로는 T-51~53(SSE·satisfy·QA).

---

## G2 — E2E 통합 · 2026-07-10 · **1차 판정: 차단** → 수정 후 재판정

### 착수 전 계약 보강 (오케스트레이터)
G0·G1 과 같은 방식으로, **구현을 시작하기 전에** 계약의 구멍을 닫았다.

- **CD-10** — `api_standard.md` 는 `/graph`·`/dashboard`·거버넌스·상위온톨로지를 요구하는데 내부 API 표에 대응 엔드포인트가 없었다.
  그대로 두면 05 는 BFF 에서 SPARQL 을 조립할 수밖에 없다(**불변원칙 1 위반**). → 내부 엔드포인트 신설, **T-55** 생성.
- **CD-11** — `KnowledgeClient.sparql(query: string)` 이 BFF 에게 쿼리 문자열 생성을 시그니처로 강제했다. 같은 원칙과 충돌.
  → **명명 질의** `POST /kg/lookup`(화이트리스트 4종, `initBindings` 바인딩)으로 대체. `sparql()` 제거.

### 산출물
| Agent | 경로 | 내용 |
|---|---|---|
| 04·06 | `knowledge/store/{lookup,graph,dashboard,governance}.py` · `reasoning/{upper_ontology,rule_views}.py` | T-55 |
| 05 | `bff/src/{routes,services/ai,schemas}` | T-50~54 |
| 07 | `frontend/src/` | T-60~62 |

### 검증 증거 — **오케스트레이터가 직접 실행** (에이전트 보고를 재검증)
| 검사 | 결과 |
|---|---|
| `pytest knowledge/tests/` | ✅ **97 passed** (G1 61 + T-55 36) |
| `bff` `npm test` | ✅ 33 passed · `typecheck` 0 errors |
| `frontend` `typecheck`·`build` | ✅ 0 errors · 빌드 성공 |
| **주입 방어 독립 검증** — `/kg/lookup` params 에 `INSERT DATA`·`DROP ALL` 주입 2종, 화이트리스트 밖 질의, `/sparql` 직접 UPDATE | ✅ 4종 모두 차단. **트리플 수 373 → 373 불변** |
| 실제 스택 `/health` (BFF→지식) | ✅ `200 ok`, `reasoner: no_jre`(예상된 폴백) |
| SSE 순서 계약 | ✅ `status·concept*·relation*·status·validation·done` |
| HITL — 위조된 `violations:[]` 로 저장 시도 | ✅ **409** (BFF 가 저장 직전 서버측 재검증) |
| HITL — `approved:false` | ✅ 409 |
| AC-1 range 위반 | ✅ `causes_range` · `severity:violation` |
| AC-8 builtin 삭제 / 비관리자 | ✅ `400 BUILTIN_LOCKED` / `403 FORBIDDEN` |
| CD-6 `X-Trace-Id` 전파 | ✅ |
| CD-7 화면 (스크린샷) | ✅ amber 위반 시 승인 체크박스·저장 버튼 **실제 비활성** |
| CD-8 화면 (스크린샷) | ✅ `satisfies:null` → ⛔ 아닌 "판정 보류" |
| 환각비교 화면 (스크린샷) | ✅ LLM 단독=점선·amber·"미검증" 라벨 / 검증답변=출처 부착 |
| **`/satisfy` 지식범위 (AC-scope)** | ❌ **실패** — 아래 D1 |
| **`/qa` mode=compare (B계층)** | ❌ **실패 422** — 아래 D2 |
| **A계층 결정론 수치** | ❌ **실패** — 아래 D3 |
| **C계층 `insufficient_evidence`** | ❌ **실패 — 도달 불가능** — 아래 CD-12 |

> 세 에이전트 모두 **mock 으로만** 자기 검증을 마쳤다. 프론트→BFF→지식서비스를 실제로 연결한 것은 이 체크포인트가 처음이고,
> 그 순간 아래 4건이 드러났다. **mock 통과는 통합 통과가 아니다.**

### G2 를 차단한 결함 (전부 실행으로 발견)

1. **D1 — BFF 가 CD-4 지식범위를 무시한다.** `/satisfy` 는 `project_id` 를 **필수로 받고서 쓰지 않는다**
   (`categories: body.categories ?? null`). 같은 설계로 프로젝트 A(소음+떨림)와 B(떨림만)를 판정하면 **둘 다 4위반**이 나온다.
   지식서비스에 `categories:["떨림"]` 을 직접 주면 `[S3,S4,S6]` 3위반으로 정확하다. **지식서비스는 맞고 BFF 가 깨뜨렸다.** AC-scope 실패.
2. **D2 — `/qa` B계층이 422 로 죽는다.** `runLayerB` 가 `require: null` 을 보내는데 `SatisfyRequest.require` 는 `list[str]` 이다.
   환각비교의 핵심 경로(설계 검증 질문)가 실제 스택에서 한 번도 성공하지 못했다. mock 이 가렸다.
3. **D3 — A계층 답변에 결정론적 수치가 없다.** `determinism:"sparql"` 인데 답변을 `lookup.rows`(`max_safe_mm=599`)가 아니라
   근거 문장 텍스트로 조립한다 → "600mm 이상이면…" 만 나오고 **599 가 없다**. 회귀 `qa_layerA_599`·계약 §4.5 와 불일치.
4. **CD-12 — `insufficient_evidence` 가 도달 불가능하다** (계약 결함, v1.3 확정).
   도메인 밖 질문("타이어 공기압")에 시드 문장 6건이 전부 근거로 실리고 `insufficient_evidence:false`. 점수는 5건이 `0.000`.
   `verified` 는 *권위*를 재는 축이지 *관련성*을 재지 않는데 `sufficient` 를 그 하나로 정의했다.
   시드 문장은 전부 지식범위 안 → 항상 `verified` → **"억지 답 금지" 가드레일이 영영 발화하지 않는다.**
   **CD-8 과 같은 종류의 결함이다 — 도달 불가능한 가드레일은 없는 것과 같다.**
   → 확정: `insufficient_evidence` = **도메인 접지 실패** OR `verified hit == 0`. 접지는 기존 `unknown_concept` 로 판정(새 엔드포인트·점수 임계값 금지).

5. **D5(위생, 차단 아님)** — `bff/src/routes/qa.ts` 가 시드 문장 S1~S6 원문과 증상→규칙 매핑을 **하드코딩**한다.
   SC-1 로 문장을 고치면 BFF 사본이 즉시 낡는다. 도메인 데이터의 진실원은 지식서비스다.

### 계약 정정 (v1.3)
- `api_standard.md` §4.4 가 자기모순이었다 — 판정 보류 경고를 한 곳은 `steps[1].warnings[]`, 다른 곳은 `steps[1].checks` 라 했다.
  fixture `satisfy_pending_missing.json` 이 정본(`warnings[]`). → 정정. (07 보고)
- `/extraction/save` 요청의 `draft_id`(멱등 키)가 §4.3 예시에 빠져 있었다. → 문서화. (07 보고)

### 2차 — 수정 후 재판정 · **G2 통과**

D1~D4 수정(05) 후 실 스택 프로브를 다시 돌리자 **22/22**. 그런데 07 이 화면에서 **아무도 보지 못한 결함 1건**을 더 찾았다.

6. **D6 — `/extraction/save` 의 정상 저장이 실 스택에서 한 번도 성공한 적이 없다.**
   BFF 가 `kgSave` forward 에서 `approved` 를 빠뜨려 지식서비스 `SaveRequest.approved: Literal[True]` 가 거부 → 항상 `422`.
   **BFF 유닛테스트 39건은 전부 통과했다.** mock 지식클라이언트가 실제 서비스라면 거부할 페이로드를 받아줬기 때문이다.
   오케스트레이터 프로브도 놓쳤다 — 저장 테스트가 전부 **음성(409) 경로**였고, **성공하는 저장을 아무도 한 번도 실행하지 않았다.**
   → 수정: BFF 가 `approved`·`draft_id` 를 채워 보낸다. 지식서비스의 `Literal[True]`(다층 방어)는 유지.
   → **`contracts/README.md` §3.1 신설**: "mock 은 계약의 하한이 아니라 계약 그 자체다." mock 엄격화 + 성공경로 단언 의무화.

### 최종 검증 증거 (오케스트레이터 직접 실행)
| 검사 | 결과 |
|---|---|
| `pytest knowledge/tests/` | ✅ **97 passed** |
| `bff` `npm test` · `typecheck` | ✅ **41 passed** · 0 errors (7회 반복 안정) |
| `frontend` `typecheck` · `build` | ✅ 0 errors · 빌드 성공 |
| `validate_contracts.py` | ✅ 스키마 6 · 검증 27건 |
| **실 스택 프로브 22항목** | ✅ **22 / 22** (`KNOWLEDGE_MOCK=false`) |
| AC-scope (CD-4) | ✅ 프로젝트 A `[S1,S3,S4,S6]` / B(떨림만) `[S3,S4,S6]` — **BFF 가 지식범위를 전달** |
| AC-2 | ✅ 설계 B(실리콘) `satisfies=true` |
| CD-8 | ✅ `200 satisfies=null` · `steps[1].warnings=2` · `checks=0` |
| **CD-12 가 no-op 이 아님** | ✅ 도메인 안 2건 → 근거 6건 / 도메인 밖 2건 → `insufficient=true`, `sources=0` |
| A계층 결정론 | ✅ `"안전 길이는 599mm 이하입니다"` — `rows` 에서 조립 |
| **정상 저장 (D6)** | ✅ `201` · `S8` · `NoiseRule`+`NoiseShape` · `m1.sentences 7→8` · 멱등 재전송 시 중복 없음 |
| 저장 가드레일 | ✅ `conditionedOn` 도메인 위반 문장 → `409` (재검증이 실제로 막는다) |
| 주입 방어 (독립 검증) | ✅ 4종 차단 · 트리플 373 불변 |
| 화면 E2E (실제 BFF) | ✅ SC-1·SC-2·SC-3 + CD-7·CD-8·CD-12 · 스크린샷 `shots/real_*.png` 10장 |

### G2 통과 조건
- [x] SC-1 → SC-2 → SC-3 가 **실제 스택**으로 화면에서 처음부터 끝까지 동작
- [x] BFF 가 판정 필드를 재해석하지 않는다(무변형 통과)
- [x] BFF 가 RDF/SPARQL/SHACL 을 만들지도 파싱하지도 않는다(CD-11 명명 질의)
- [x] 가드레일이 **도달 가능**하고 실제로 발화한다(CD-7·CD-8·CD-12·HITL 재검증)

**판정: 통과.** 임계 경로는 이제 T-70(QA 게이트) → T-80(패키징).

### 3차 — **실키(Claude) 검증** · 2026-07-10 · **판정 철회 → 재수정 중**

재현님이 실제 `ANTHROPIC_API_KEY` 사용을 허가해, `AI_MOCK_MODE=false` + `claude-opus-4-8` 로 전 스택을 재검증했다.
**mock 폴백이 아님을 먼저 확인했다** — `llm_answer.model == "claude"`. (`/health.llm_provider` 는 설정값일 뿐이라 증거가 못 된다.)

#### 확인된 것 (mock 이 가리지 않았던 부분)
| 검사 | 결과 |
|---|---|
| Anthropic API 가 BFF 요청 형태를 수용하는가 | ✅ `output_config.format` structured output 수용 · 열거형 강제 · `claude-opus-4-8` |
| `temperature` | ✅ Opus 4.8 은 400 으로 거부 — 05 의 주석대로. structured output 으로 결정론 확보 |
| **API 키 노출** | ✅ 로그에 `sk-ant` **0건** (불변원칙 6) |
| **판정 필드의 결정론성** | ✅ `satisfies`·`violations` 는 LLM 과 무관 (불변원칙 3 유지) |
| 분류 결정론 | ✅ 같은 질문 3회 → 동일 계층 |
| 실키 프로브 22항목 | **20 / 22** |

#### CD-13 — 실키만이 드러낸 결함 (G2 판정 철회 사유)

```
"타이어 공기압은 얼마로 맞춰야 하나요?"  → layer=A insufficient=false sources=[S1]
     답변: "겨울철 저온에서 고무는 경도가 상승해 소음을 유발한다."
"엔진 오일 교환 주기는?"                → layer=A insufficient=false sources=[S1]
"자전거 체인에 실리콘 윤활유 써도 될까?" → layer=C insufficient=false sources=[S1..S6]  ← 시드 전부
"노트북에 알루미늄 700mm 써도 될까?"    → layer=B insufficient=false sources=8건 · 확정 판정
```

`mode:"verified"` 다. **"검증 답변"이라는 라벨을 달고 거짓 출처를 제시한다.** LLM 환각보다 나쁘다 —
환각은 미검증으로 표시되지만, 이것은 시스템이 권위를 부여한 거짓이다.

두 가지 원인이 겹쳤다.

1. **가드레일이 라우팅 뒤에 있었다.** CD-12 도메인 접지를 `runLayerC` 안에만 두었는데, **계층은 LLM 분류기가 고른다.**
   분류가 A·B 로 가면 접지는 실행조차 되지 않는다. mock 분류기는 이 질문들을 전부 C 로 보냈기에 통과했다.
   **가드레일 뒤에 라우팅을 두면 라우팅이 우회로가 된다.**
2. **각 계층이 없는 입력을 지어냈다.** A 의 명명질의는 무조건 폴백(`symptom_causes(Noise)`)이라 `rows` 가 절대 비지 않았고,
   B 의 `parseDesign` 은 기본 설계(`Rubber/600/8/simple/MidSizeSUV/Winter`)를 날조해 노트북 질문에도 확정 판정을 냈으며,
   C 의 접지는 `실리콘` 하나만 스쳐도 통과했다.
   **지어낸 입력은 결정론 엔진을 통과해 *권위 있는 거짓*이 된다.**

가장 서늘한 대목: 실제 Claude 는 답변 **문장**에서 "제공된 근거만으로는 답변할 수 없습니다"라고 스스로 물러섰다.
**계약 필드만 거짓말을 했다.** 즉 **가드레일이 LLM 의 선의에 의존하고 있었다** — 결정론 우선(불변원칙 3)의 정면 위반이다.

→ **CD-13(v1.4)**: 접지를 라우팅보다 앞에 두고, 전 계층을 fail-closed 로. 입력 날조 금지. `insufficient` 면 `sources:[]`.

**G2 판정을 철회한다.** CD-13 수정 후 실키로 재판정한다.

#### CD-14 — CD-13 수정이 옆에서 같은 병을 재발시켰다

CD-13 대로 `parseDesign` 이 값을 지어내지 않게 되자, 수치 부족 질문에서 satisfy 가 **CD-8 판정 보류**를 반환하고
`violations` 가 비고 → `sources` 가 비고 → `runLayerB` 가 `gw.answer(question, [])` 를 호출했다.

**그런데 `answer(q, [])` 는 환각비교의 `llm_answer` 를 만드는 바로 그 호출이다** — 시스템 프롬프트가
"근거 없이 일반 지식만으로 답하라"로 갈린다. 결과:
```
"중형 SUV에 고무 600mm 써도 될까?"  →  determinism:"satisfy"  sources:[]  insufficient:false
verified_answer.text = "## 답변 … 일반적인 설계 지식에 기반한 답변입니다 …"
```
**`verified_answer` 와 `llm_answer` 를 같은 함수로 만든 것이 화근이다. 근거가 비는 순간 둘이 같아진다.**
(오케스트레이터 프로브도 놓쳤다 — `layer=B, insufficient=false` 만 단언하고 답변이 근거에 기반했는지 보지 않았다.)

→ **CD-14(v1.5)**: `sources` 가 비면 `verified_answer.text` 를 LLM 이 생성하지 않는다. B 판정 보류는 결정론 텍스트.
`answer(question, sources)` 는 빈 근거에서 **throw** 하고, 무근거 답변은 `llmOnlyAnswer(question)` 전용 함수로만 만든다.
**두 목적을 한 함수에 두지 않는다 — 타입으로 가른다.**

#### 재판정 — 실키 · **G2 통과**

| 검사 (전부 `AI_MOCK_MODE=false`, `claude-opus-4-8`) | 결과 |
|---|---|
| 실키 프로브 22항목 | ✅ **22 / 22** |
| **가드레일 우회 공격 8종** (오케스트레이터가 설계) | ✅ **8 / 8 차단** (우회 성공 0) |
| B 수치부족 → 판정 보류 · LLM 미호출 | ✅ `"판정 보류 … 누락된 값: springN"` · `sources:[]` |
| B 수치완전 → 확정 + 출처 (no-op 아님) | ✅ `sources=[S3,S4,S6,ArmRule,ChatterRule,SpringRule]` |
| A 결정론 수치 | ✅ `"안전 길이는 599mm 이하"` |
| C 정상 질의 | ✅ 근거 6건 |
| 환각비교 (분리 후) | ✅ `llm_answer.model="claude"` 계속 생성 |
| `bff` `npm test` | ✅ **49 passed** · typecheck 0 (5회 반복 안정) |
| `pytest knowledge/` | ✅ 97 passed |
| `validate_contracts.py` | ✅ 27건 |
| `frontend` typecheck·build | ✅ |
| **API 키 노출** | ✅ 로그에 `sk-ant` 0건 |

우회 공격 8종(오케스트레이터 설계, 도메인 개념을 섞어 접지 게이트를 통과시키려는 시도 포함):
`타이어 공기압` · `엔진 오일 교환 주기` · `자전거 체인 실리콘` · `노트북 알루미늄 700mm` ·
`자전거 체인에 실리콘을 바르면 소음이 줄어드나요?` · `타이어 고무는 겨울철에 소음이?` ·
`신발 밑창 고무도 겨울에 경도가 상승해 소음이?` · `실리콘 귀마개는 소음을 해소하나요?`
→ **전부 `insufficient_evidence:true`, `sources:[]`.**

**판정: 통과.**

#### D8 — 실키 조사 중 발견한 별건 (Phase 3 로 넘김)

`unknown_concept` 의 **구현이 계약과 다르다.** CD-7 은 "범주 밖 개념"이라 정의했는데,
`/validate/shacl` 은 **`concepts[]` 배열 자기참조**만 검사한다(관계가 참조하는 라벨이 배열에 없으면 발화).
실측: `concepts=[고무, 자전거]` + `고무 causes 자전거` → `unknown_concept` **없음**(`causes_range` 만).
즉 **온톨로지 소속을 전혀 보지 않는다.**

그런데 라벨→IRI 해석기는 **이미 있다**(`고무→dom:Rubber`, `소음→dom:Noise` 를 `offender_iri` 로 반환).
또 기존 명명질의 `concept_relations` 는 IRI 로컬네임 기준으로 알려진/미지 개념을 결정론적으로 가른다
(`Rubber→rows=1`, `Bicycle→rows=0`). **새 엔드포인트 없이 닫을 수 있다.**

영향: CD-13 의 C계층 도메인 접지가 현재 **추출기(LLM)의 도메인 엄격성에 의존**한다.
실측 8/8 차단이지만 **하드 보장이 아니다**(05 가 정직하게 보고했고, 확인했다).
`unknown_concept` 를 계약대로(온톨로지 소속) 고치면 접지가 결정론이 된다.

**주의 — 과차단 위험**: 실제 Claude 는 `"겨울철 저온"` 같은 라벨을 낸다. 온톨로지 소속 검사를 켜면
정상 질문까지 미지 개념으로 막힐 수 있다. **회귀셋으로 측정한 뒤** 켜야 한다.
→ **T-73**(04 소유, Phase 3). 08 QA 의 환각 루브릭(T-71)과 함께 검증한다.

### 이번 페이즈의 교훈
**mock 통과는 통합 통과가 아니다.** G2 를 막은 결함 6건 중 5건이 mock 에서는 보이지 않았다.
그중 D1(지식범위 무시)은 **에러조차 내지 않고 `200` 과 함께 조용히 틀린 판정을 반환했다** — 가장 위험한 종류다.
세 에이전트 모두 "자기 검증 완료"를 보고했지만, 실제로 세 서비스를 연결한 것은 통합 체크포인트가 처음이었다.

**그리고 실 스택 통과도 실키 통과가 아니었다.** 22/22 를 통과한 그 스택이, 실제 LLM 을 붙이자마자
도메인 밖 질문에 시드 문장을 근거로 붙여 답했다(CD-13). mock 분류기가 모든 질문을 C계층으로 보내
가드레일이 있는 쪽으로만 흘려보냈기 때문이다. **mock 은 결함을 숨긴 게 아니라, 결함을 만나지 않는 경로만 골라 갔다.**

가드레일 설계 원칙 넷 — 전부 이 프로젝트에서 값을 치르고 얻었다:
1. **도달 가능해야 한다** (CD-8·CD-12) — 발화할 수 없는 가드레일은 없는 것과 같다.
2. **우회 불가능해야 한다** (CD-13) — 가드레일 앞에 분기가 있으면 그 분기가 우회로다.
3. **없는 입력을 지어내지 않는다** (CD-13) — 날조된 입력은 결정론 엔진을 통과해 권위 있는 거짓이 된다.
4. **막다른 길에서 LLM 으로 흘러내리지 않는다** (CD-14) — 근거가 없으면 답하지 않는다. 답을 *만들어내지* 않는다.
   검증답변과 무근거답변을 **같은 함수로 만들면**, 근거가 비는 순간 둘이 같아진다. 타입으로 가른다.

그리고 가드레일 하나를 고칠 때마다 **옆에서 같은 병이 재발했다**(CD-12 → CD-13 → CD-14).
공통 원인은 하나다: **판정 경로 어딘가에 "값이 없으면 그럴듯한 것으로 채운다"는 코드가 있었다.**
기본 질의, 기본 설계, 기본 답변. 셋 다 없앤 뒤에야 닫혔다.

### 미결 — 다음 게이트로 넘긴다
- **BFF 테스트 스위트의 산발적 실패**를 2회 관측했다(서로 다른 파일·테스트). 출력을 보존하지 못했고 이후 **37회 재현 실패**.
  소켓 재사용 가설을 세워 직접 재현 실험을 했으나 **반증되었다**. `test/util.ts` 에 서버별 커넥션 풀 격리를 넣었지만
  **그 실패의 검증된 수정이 아니다.** 재발 시 전체 출력을 반드시 보존할 것. T-82(CI)에서 결정론을 강제한다.
- `POST /upper-ontology/classes` 는 승인 게이트까지만 — 승인된 변경의 TTL 영속화 미구현(04 보고).
- Idempotency·CircuitBreaker 상태가 **in-memory** — 프로세스 재기동·다중 인스턴스에서 무효(05 보고).
- 실키(Claude/Gemini) 경로는 **미검증**. mock 폴백이 분류 정확도·환각비교 품질을 가린다.
- **Idempotency 는 BFF 프로세스 메모리**다. 같은 `draft_id` 라도 **BFF 재기동 후 재전송하면 중복 저장된다.**
  진짜 멱등은 `kg/save` 의 `draft_id` 유니크 제약이 필요하다(Phase 3).
- `/graph` 의 `inferred` 엣지는 시드에 1건뿐이고 증상·문장 필터 질의에는 나타나지 않는다. AC-4 점선 로직은 정상이나
  **시드가 추론 엣지를 거의 만들지 않는다**. 08 QA 는 inferred 가 실제로 렌더되는 질의를 회귀셋에 넣어야 한다.
- 실 스택 검증으로 개발 스토어에 `S7`·`S8` 이 런타임 추가되었다(`knowledge/data/` 는 gitignore 대상 — 커밋 오염 없음).
  T-82 CI 는 임시 데이터 디렉터리로 격리해야 한다.

### 다음
Phase 3(08 QA 게이트 → 09 패키징) 착수 **승인 요청**. 임계 경로는 T-70(회귀셋·AC-1~8) → T-80(Docker·JRE).
