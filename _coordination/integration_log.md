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
