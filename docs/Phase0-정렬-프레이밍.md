# PKMS × Ontology 통합 재기획 — Phase 0 : 정렬·프레이밍

> 작성일 2026-07-09 · 상태 **draft-v0.1 (검토용)**
> 근거 폴더: `Working/PKMS-Ontology`(허브·요구사항 지시문), `Working/pkms-dev-system`(성숙 앱), `Working/OntologyResearch`(pkms-web·SPMM·와이퍼 TTL·온톨로지 방법 라이브러리)
> 이 문서는 재기획 6단계 프로세스의 1단계 산출물이다. 목표/비목표/페르소나/인벤토리는 재현님 레드라인 후 확정한다.

---

## 1. 배경·목적

지금 "PKMS"는 사실상 **두 개의 구현체**로 갈라져 있다. 이번 재기획의 목적은 두 구현의 검증된 기능을 **하나의 시스템으로 통합**하고, 그 과정에서 요구사항·기능구조·화면·시나리오를 처음부터 다시 정리하는 것이다. 도메인 지식은 **와이퍼 설계 6문장**, 논리 온톨로지는 **SPMM을 확장**해 사용하며, OWL의 표현력을 정면으로 활용한다.

---

## 2. 확정된 프레이밍 (2026-07-09 대화)

| 항목 | 결정 | 근거 |
|------|------|------|
| **1차 정체성** | **엔지니어 실무 지식도구** (암묵지 입력→온톨로지 지식맵→설계검증) | 재현님: "1번이면서 2번도 보여줄 수 있어야" |
| **2차(시연) 기능** | **온톨로지×LLM 환각저감**을 화면에서 토글로 시연 가능한 1급 기능으로 | 위 |
| **통합 백본** | **pkms-dev-system 베이스 + pkms-web 이식** | 성숙 UX + 진짜 OWL/SHACL을 동시에 확보 |
| **진행 순서** | 정렬 → 온톨로지 백본 → 시나리오 → 기능구조도 → 화면설계 → 검증 | 백본을 먼저 굳혀 이후 설계의 기준선으로 |

---

## 3. 목표 / 비목표  *(draft — 검토 요청)*

**목표(Goal)**
- 와이퍼 설계 6문장을 SPMM 확장 온톨로지 위에 올려, 자연어 지식 입력 → 구조화 → **지식맵** → **설계 검증**까지 한 흐름으로 지원한다.
- LLM 추출·Q&A 결과를 OWL 추론 + SHACL로 검증해, "명세 위반 = 환각 후보"를 화면에서 즉시 보여준다(환각비교 모드).
- 관리자는 상위 온톨로지(SPMM)를, 엔지니어는 도메인 지식을 각각 편집·검증한다(역할 분리).

**비목표(Non-Goal)** — 최소 3개 명시
- ⛔ 규정 PDF 대량 자동추출 파이프라인(개발계획서 화면2의 문서업로드→LLM추출)은 이번 통합 범위에서 **보류**(6문장 시드에 집중).
- ⛔ GPU·자체호스팅이 필요한 기법(K-ON·KG-FIT·OntoTune 파인튜닝)은 이번 범위 밖. 외부 API(Claude/Gemini) + 결정론적 reasoner로 한정.
- ⛔ FMEA 자동생성·보고서 출력(Phase 3 거버넌스)은 후속.
- ⛔ 다중 도메인 확장(와이퍼 외 도메인)은 이번엔 하지 않음 — 와이퍼 단일 도메인으로 깊이 우선.

---

## 4. 주 사용자 페르소나  *(draft — 검토 요청)*

| ID | 페르소나 | 상황·목적 | 핵심 관심 |
|----|----------|-----------|-----------|
| **P1** | **제품설계 엔지니어** | 와이퍼 설계 중 암묵지를 남기고, 자기 설계가 규격·요구를 만족하는지 확인 | 지식 입력 편의, 설계검증(satisfy), 근거·출처 |
| **P2** | **지식/온톨로지 관리자** | 상위 온톨로지(SPMM)·도메인 개념/관계·SHACL 제약을 유지·거버넌스 | 일관성, 버전·영향분석, 권한 |
| **P3** | **연구자·학습자 / 세미나 청중** | "온톨로지가 있으면 환각이 준다"를 눈으로 확인·학습 | 환각비교, 위반 설명(왜), 신뢰지표 |

---

## 5. 두 시스템 기능 인벤토리 — 계승 / 이식 / 재구성 / 보류

| 기능 | 출처 | 처리 | 비고 |
|------|------|------|------|
| SmartInput (LLM 추출·SSE·엔티티 하이라이트) | dev-system | **계승** | 생성기 슬롯 |
| /extraction/validate (추출→OWL/SHACL 검증) | dev-system | **계승** | 생성기–검증기 핵심 |
| LogicEditor (IF-THEN, React Flow) | dev-system | **계승** | 규칙 편집 |
| Q&A (RAG) | dev-system | **계승→강화** | pkms-web의 Layer A/B 2레이어로 재구성 |
| VisualDiff (서브그래프 비교) | dev-system | **계승** | 설계안 비교 |
| OntologySpec (도메인 개념/관계 DL 명세) | dev-system | **계승** | M1 편집 |
| UpperOntology 편집기 (SPMM·관리자·custom CRUD·지식맵) | dev-system | **계승** | M0 편집 (화면1) |
| AI Gateway (Claude/Gemini/Mock) | dev-system | **계승** | Generator |
| reasoner 사이드카 (owlready2+HermiT+pySHACL) | dev-system | **계승→확장** | satisfy 엔진 추가 |
| M0/M1/M2 3층 명시 모델·상태 대시보드 | pkms-web/계획서 | **이식** | 층 구분을 UI 전면화 |
| 환각비교 모드 (LLM 단독 vs 온톨로지, 3-토글) | pkms-web/계획서 | **이식(전면화)** | 시연 1급 기능 |
| SHACL explain (위반 자연어 설명, xpSHACL식) | pkms-web | **이식** | "왜 위반인가" |
| Q&A Layer A(규칙질문)/B(설계검증질문) | pkms-web | **이식** | 2레이어 QA |
| 지식맵 (RDF/SPARQL viz ↔ 지식문장맵) | 양쪽 | **재구성** | 통합 지식맵 뷰 |
| **satisfy 검증(DB ⊑ RB subsumption + SHACL 게이트)** | SPMM 스펙(신규) | **신규 도입 후보** | OWL 최강 활용점 |
| 규정 PDF 추출 파이프라인 | 계획서 화면2 | **보류** | 비목표 |
| OntoTune·KG-FIT·K-ON | 계획서 4축 | **보류(선택)** | GPU 필요 |
| FMEA·보고서 출력 | dev-system Phase3 | **보류** | 후속 |

---

## 6. 온톨로지·OWL 관찰  *(Phase 1 입력)*

현재 자산에는 "SPMM"이 **두 형태**로 존재한다 — 이번 재기획의 핵심 갈림길이다.

- **(가) 도메인-슬라이스 SPMM** (`data/m0/spmm.ttl`) : PartType·Material·VehicleType·Component·EnvCondition·Symptom + hasMaterial·mountedOn·operatesIn·causesSymptom + AllDisjointClasses. 와이퍼 6문장의 **증상·인과 구조**에 직결. 단순·명확.
- **(나) 정통 SPMM (FBS, 2012)** : Entity/Form/Behavior(**Required/Designed/Test**)/Attribute + 9관계(is_form_of·has_des_behavior·has_subbehavior(transitive)·has_attribute·**satisfy_beh_required** 등). 핵심은 **satisfy(DB ⊑ RB)를 DL 서브섬션으로 판정** — "설계가 요구를 만족하는가"를 기계가 증명. 앱의 `spmmMapping.ts`가 이 어휘(Artifact·Behavior·Attribute·DesignedBehavior)로 정렬돼 있음.

와이퍼 6문장은 현재 **증상-인과 중심**(겨울철→소음, 길이→떨림)으로 모델링돼 있어 (가)에 잘 맞는다. 하지만 (나)의 **satisfy 서브섬션**이야말로 OWL을 정면 활용하는 지점이자, "LLM이 제안한 설계 ⊑ 요구인가"를 reasoner가 증명/반증하는 **환각가드 데모의 최강 소재**다. 두 시스템을 통합한다면 (나)를 진짜 상위층으로 두고 (가)의 구조·증상 어휘를 그 아래 도메인 중간층으로 배치하는 **하이브리드 2층**이 자연스럽다 — Phase 1에서 결정.

---

## 7. Phase 1 결정 항목 — **확정 (v0.2, 2026-07-09)**

1. **SPMM 채택 수준** → 정통 SPMM(FBS)에 **증상·인과·제품구조 상위어 확장**(하이브리드를 M0 안으로).
2. **M0/M1/M2 계층 + OWL2 punning** → **유지**.
3. **저장 모델** → **RDF/SHACL 단일화**(Neo4j 미채택 — 현 규모에서 불필요).
4. **OWL 프로파일** → **EL + SHACL 이중화 유지**, satisfy 표현력은 EL+SHACL 조합으로 확보.
5. **와이퍼 문장** → 증상-인과 **유지 + 요구-설계 만족으로 확대**(R1·R2·D1).
6. **satisfy 수치 보완** → SHACL 게이트 + **구간 비교기**(SMT는 비목표).

→ 상세는 [Phase1-온톨로지-백본.md](Phase1-온톨로지-백본.md) v0.2.
