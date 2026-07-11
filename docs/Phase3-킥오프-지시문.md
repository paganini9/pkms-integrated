# Phase 3 킥오프 지시문 — 검증·패키징 (QA 먼저 · DevOps 병렬)

> 현재 상태(task_board.md 권위): **G0·G1·G2 통과, Phase 2(통합) 완료.** 실키(`claude-opus-4-8`) 프로브 22/22 · 우회공격 8/8 차단 · pytest 97 · vitest 49 · 계약검증 27.
> 이제 **Phase 3(검증·패키징)** 만 남았다. 목표: 릴리스 가능 상태(오케스트레이터 §5 통합 게이트 전 항목 통과 + Docker 패리티 + CI).
> **선행**: `docs/템플릿잔재-PKMS정정-지시.md` 를 먼저 적용(오케스트레이터·작업분해 맵을 PKMS 로 정정)한 뒤 착수한다. 그래야 08·09 가 올바른 표면(`/api/v1/extraction·satisfy·qa·graph`)을 기준으로 검증한다.

---

## 0. 배치 원칙

- **08 QA 가 게이트**다: 회귀셋·수용기준을 먼저 세워 "무엇이 통과인지"를 고정한다(T-70→71→72). 04 의 T-73은 회귀셋으로 **측정한 뒤** 켠다(과차단 위험).
- **09 DevOps 는 병렬**: Docker/시드적재/CI(T-80~82)는 QA와 독립적으로 진행하되, CI(T-82)는 QA 회귀셋을 게이트로 물린다.
- **미결 리스크를 정식 태스크로 승격**(T-83~87 + 가드): integration_log 의 "미결"을 떠다니게 두지 않는다. 각 항목에 owner·DoD 부여.
- **원칙(값을 치르고 얻은 것)**: mock 통과 ≠ 통합 통과 ≠ 실키 통과. **게이트는 실 스택·실키**로 판정한다. 결정론 경로에 "값 없으면 그럴듯한 것으로 채우기" 금지.

## 1. 태스크 (기존 + 승격)

### 08 QA (게이트, 먼저)
| id | task | DoD |
|----|------|-----|
| T-70 | 회귀셋 확장(`regression_set.jsonl`) + 수용기준 AC-1~8 | 전건 통과. **가드레일 우회 8종** 포함. **inferred 엣지가 실제 렌더되는 질의** 포함(AC-4). |
| T-71 | LLM-as-Judge 루브릭(정확성·근거성·안전성·RAG충분성) | 결정론 100% 일치, 미검증 근거 0. **실키로 검증**(mock 통과는 무의미). |
| T-72 | 실패 케이스(타임아웃·range위반·수치누락·도메인밖·롤백) | 수용기준 §4 전건. |

### 04 (QA 측정 후)
| id | task | DoD |
|----|------|-----|
| T-73 | `unknown_concept` 를 계약(CD-7 "범주 밖 개념"=온톨로지 소속)대로 수정 | 라벨→IRI 해석기·`concept_relations` 재사용(새 엔드포인트 없음). **과차단 위험**: 실 LLM 라벨("겨울철 저온")로 회귀셋 측정 후 켠다. T-71 루브릭과 함께. |

### 09 DevOps (병렬)
| id | task | DoD |
|----|------|-----|
| T-80 | Dockerfile ×3 + compose(**HermiT JRE 포함**) | 로컬=Docker 동일 동작. `/health.reasoner` 가 JRE 유무 반영. |
| T-81 | 시드 자동적재 · 벡터 초기 인덱싱 · env 배선 | 최초 기동만으로 6문장 조회 가능. **로컬 임베딩 모델 캐시**(이미지/볼륨)로 오프라인 기동. |
| T-82 | CI: `validate_contracts.py` + typecheck + 회귀셋 + **실 스택 스모크** | 계약 위반 시 빌드 실패. mock 통과만으로 통과 금지(§3.1). 임시 데이터 디렉터리 격리. |

### 승격된 미결 리스크 (신규 정식 태스크)
| id | owner | task | DoD |
|----|:--:|------|-----|
| T-83 | 06·05 | **진짜 멱등**: `kg/save` 에 `draft_id` 유니크 제약 | BFF 재기동/다중전송에도 중복 저장 0(현재 in-memory idempotency 한계 해소). |
| T-84 | 05 | Idempotency·CircuitBreaker 상태 **외부화 검토** | 최소: 단일 인스턴스 가정 명시+문서화. 이상: 영속/공유 스토어. 재기동·다중 인스턴스 동작 규정. |
| T-85 | 04 | 상위 온톨로지 승인 후 **TTL 영속화** 구현 | `POST /upper-ontology/classes` 승인 변경이 TTL 에 반영·재기동 후 유지(현재 승인 게이트까지만). |
| T-86 | 08·09 | BFF 테스트 **flaky 근절** | 재발 시 **전체 출력 보존**(37회 재현 실패 이력). T-82 에서 결정론 강제. 원인 확정 전 "수정됨" 선언 금지. |
| T-87 | 02·08 | 시드에 **inferred 엣지 생성 질의** 보강 | 지식맵 점선(AC-4)이 실제 렌더되는 질의를 회귀셋에. (현재 inferred 1건, 필터 질의엔 미노출.) |
| 가드 | 04·03 | **컬렉션-임베더 일치 가드**(하드닝) | Chroma 컬렉션 메타에 `embedder_model`·`embed_dim` 저장, 불일치 시 drop→recreate. provider 전환 시 "data/chroma 삭제 깜빡" 계열 무증상 오류 구조적 차단. `MockEmbedder.DIM`도 `settings.embed_dim` 참조. |

## 2. 릴리스 게이트 (Phase 3 종료 조건)

오케스트레이터 §5 통합 게이트 전 항목 + 위 태스크 done:
- 추적성 SC-1~4·6~8 → FR → 구현 → 테스트, 계약 준수, 경계(외부=BFF `/api/v1`만), 안전(근거부족 분기), 신뢰성(Timeout/Retry/Breaker/Idempotency ≥2, **T-83 멱등 포함**), 재현성(결정론 검증), QA(회귀셋·AC 전건·환각 0·출처 100%, **실키**), 패키징(로컬=Docker).
- 통과 시 `릴리스_노트.md` + 태그 `g3-release`.

## 3. 제약 (불변)

레이어 분리(지식·추론·RAG는 knowledge만) · 내부 비노출(BFF만 외부 `/api/v1`) · 키는 시스템 환경변수(코드·.env·git 금지·로그 마스킹, 앱 AI=Solar `Studio_API_Key`) · **결정론 우선**(satisfy·SHACL·reasoner > LLM) · **실 스택·실키로 게이트**(mock 통과 무의미) · 테스트 우선 · 모든 산출 한글 · 각 단계 한글 커밋 + `git push origin develop`.

## 4. 오케스트레이터 붙여넣기 프롬프트

```
Phase 2(G2)까지 통과했다(task_board 확인). 이제 Phase 3(검증·패키징)를 수행한다.

선행: docs/템플릿잔재-PKMS정정-지시.md 를 먼저 적용해 00_오케스트레이터_지시문·작업분해_의존성맵의 MacroLens 잔재를 PKMS로 정정한다.

그 다음 Phase 3 를 배치한다(QA 먼저 게이트, DevOps 병렬):
- 08 QA: T-70 회귀셋+AC-1~8(우회 8종·inferred 렌더 질의 포함) → T-71 LLM-as-Judge(실키 검증) → T-72 실패 케이스.
- 04: T-73 unknown_concept 를 온톨로지 소속 검사로. 단 T-70 회귀셋으로 과차단을 측정한 뒤 켠다(실 LLM 라벨 대응).
- 09 DevOps(병렬): T-80 Dockerfile×3+compose(HermiT JRE), T-81 시드 자동적재·벡터 초기 인덱싱·로컬 임베딩 모델 캐시, T-82 CI(validate_contracts+typecheck+회귀셋+실스택 스모크).
- 미결 리스크를 정식 태스크로: T-83 kg/save draft_id 유니크 멱등, T-84 Breaker/Idempotency 외부화 검토, T-85 상위 온톨로지 승인 TTL 영속화, T-86 BFF flaky 근절(재발 시 출력 보존, 원인 확정 전 수정 선언 금지), T-87 시드 inferred 엣지 보강, 가드: 컬렉션-임베더 일치(메타 model·dim, 불일치 시 재생성; MockEmbedder.DIM=settings.embed_dim).

게이트: 실 스택·실키로 판정(mock 통과 무의미). 결정론 경로에 "값 없으면 채우기" 금지. 각 단계 한글 커밋+push. Phase 3 종료 시 오케스트레이터 §5 전 항목 통과 확인 → 릴리스_노트.md + 태그 g3-release. 착수 전 task_board 에 위 태스크(deps·DoD) 전개하고 배치 계획을 보고한다.
```
