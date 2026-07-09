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
