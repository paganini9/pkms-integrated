# PKMS × Ontology 통합 재기획 — Phase 1 : 온톨로지 백본

> 작성일 2026-07-09 · 상태 **draft-v0.2 (검토용)**
> 확정 전제(Phase 0): 하이브리드 2층 · 주 대상 P1 엔지니어/P2 관리자 · 실무도구+환각저감 시연 · 목표/비목표 유지
> **확정(Phase 1 v0.2, 2026-07-09 대화 반영)**:
> - SPMM 정통(FBS)에 **증상·인과·제품구조 상위어를 확장**해 M0로.
> - **satisfy(DB⊑RB) 서브섬션 유지** + **수치 보완**(SHACL 게이트 + 구간 비교기).
> - **OWL2 punning 유지**.
> - **저장모델 = RDF/SHACL**(Neo4j 미채택 — 현 규모에서 불필요).
> - **OWL EL + SHACL 이중화 유지**, satisfy에 필요한 표현력은 EL+SHACL 조합으로 확보.
> - 와이퍼 6문장: **증상-인과 유지 + 요구-설계 만족으로 확대**.

---

## 1. 계층 구조 (M0 확장 상위 + M1 도메인 + M2 인스턴스)

| 층 | 명칭 | 구성 | 소유 |
|----|------|------|------|
| **M0** | 확장 SPMM 상위 온톨로지 | **M0-core**(SPMM FBS) + **M0-ext**(증상·인과·제품구조 상위어) | 관리자(P2) |
| **M1** | 와이퍼 **도메인 지식**(재사용) | 와이퍼 개념(punning) + 6문장 + DesignRule | 관리자 큐레이트·엔지니어 기여 |
| **M2** | **프로젝트 데이터** | Project + RequiredBehavior(요구) + DesignedBehavior/설계 인스턴스 | 프로젝트 엔지니어(P1) |

> **도메인 지식(M1) ↔ 프로젝트(M2) 구분**: M1은 "겨울철 고무→소음" 같은 재사용 지식, M2는 "이 프로젝트는 소음 없어야" 같은 특정 프로젝트의 요구·설계. **RB/DB는 M1이 아니라 M2 프로젝트 데이터**다(자연어로 입력 — [RB-저작-검토.md] 참조). M1 지식은 **카테고리로 그룹화**되고 프로젝트는 **적용 지식을 선택**한다(satisfy는 선택 지식만). 지식의 진실원은 **자연어 문장** — 규칙·SHACL은 LLM/컴파일러 파생([지식-저작-상호작용-검토.md]).

- 층간: M1→M0 `rdfs:subClassOf`/`subPropertyOf`, M2→M1 **`rdf:type`만**.
- **OWL2 punning(clabject) 유지**: M1 개념은 M0의 individual(ABox₂)이자 M2의 타입(TBox₁).
- 이전 v0.1의 "M1-mid 구조·증상 슬라이스"는 **M0-ext 상위어로 승격**되어 M0에 흡수된다(재사용성↑).

---

## 2. M0 — 확장 SPMM 상위 온톨로지

### 2.1 M0-core : SPMM FBS (정통)

**클래스 (4대 범주, 상호 disjoint)**: `Entity`(→SpecifiedEntity·Artifact) · `Form`(→Material) · `Behavior`(→RequiredBehavior·DesignedBehavior·TestBehavior) · `Attribute`.

**관계 (SPMM 9관계)**: `is_form_of` · `is_involved_in` · `is_feature_of` · `has_req_behavior` · `has_des_behavior` · `has_test_behavior` · **`satisfy_beh_required`(DB→RB, DB⊑RB로 해석)** · `has_subbehavior`(transitive) · `has_attribute`.

### 2.2 M0-ext : 증상·인과·제품구조 상위어 (SPMM 확장) ★ 이번 확장

정통 SPMM에 **증상과 인과 구조를 표현하는 상위 용어**를 도메인 독립적으로 확장한다.

**확장 클래스**
- `FailureBehavior ⊑ Behavior` — 관찰되는 실패/결함 거동. `Symptom ⊑ FailureBehavior`(예: 소음·떨림).
- `EnvCondition ⊑ Attribute` — 운용 환경 맥락 속성.
- **제품구조 상위어**: `PartType ⊑ Artifact`, `Component ⊑ Artifact`, `VehicleType ⊑ Artifact` (Material은 SPMM `Form` 분지).

**확장 인과 관계 (상위어, 재사용 가능)**
| 관계 | domain → range | 특성 | 의미 |
|------|----------------|------|------|
| `causes` | Behavior∪Attribute → FailureBehavior | — | 설계 요인이 증상을 유발 |
| `mitigates` | Behavior∪Attribute → FailureBehavior | — | 요인이 증상을 해소 |
| `aggravates` | Behavior∪Attribute → FailureBehavior | — | 요인이 증상을 악화 |
| `conditionedOn` | FailureBehavior → EnvCondition | — | 증상이 특정 환경 조건에서 성립 |

> 이 확장으로 SPMM의 요구·설계·시험 거동(FBS) 위에 **증상-인과 어휘**가 상위 재사용 용어로 얹혀, satisfy(요구충족)와 FMEA식 인과분석을 같은 온톨로지에서 다룬다.

**disjoint**: `AllDisjointClasses(Entity, Form, Behavior, Attribute)` + `RequiredBehavior`·`DesignedBehavior`·`TestBehavior` 상호 disjoint.

---

## 3. satisfy 메커니즘 + 수치 보완 ★

satisfy 판정은 **세 단계 결합**으로 한다(subsumption만으로 수치가 어려운 점 보완).

```
satisfy(DB, RB)  ⟺  (1) 정성 서브섬션 ∧ (2) 수치 게이트 ∧ (3) 무증상
```

| 단계 | 담당 | 내용 |
|------|------|------|
| **(1) 정성 subsumption** | OWL **EL**(HermiT/ELK) | 재질·형상·구조 등 비수치 제약에서 `DB ⊑ RB` 분류. |
| **(2) 수치 게이트** | **SHACL(CWA)** + **구간 비교기** | 길이·압력·단위 등 수치 판정. SHACL이 임계(minInclusive 등)·SPARQL 비교(`길이 > maxSafe`)를, **구간 비교기**가 구간 포함(예: `길이≤550 ⊑ 길이<600`, `압력≥12N ⊑ 압력≥10N`)을 결정론적으로 판정. |
| **(3) 무증상** | 규칙(SHACL/SPARQL) | 6문장 DesignRule을 적용해 DB가 RB가 금지한 Symptom을 유발하지 않음을 확인. |

- 셋 다 통과 → **satisfy ✔** + justification(어느 단계·어느 문장/규칙이 근거인지).
- 하나라도 실패 → **✘** + 위반 단계·문장·값 지목.

**수치 보완의 위치**: 순수 DL 데이터타입 추론은 구간 포함까지는 처리하나 복합 물리식은 한계다. 본 시스템은 **SHACL 게이트 + 경량 구간 비교기**로 와이퍼 도메인의 선형 수치 제약(임계·구간)을 결정론적으로 커버한다. 비선형·연성(coupled) 물리식이 필요한 미래 도메인에서는 SMT solver 결합이 업그레이드 경로(에스컬레이션) — **현재는 비목표**.

---

## 4. OWL 프로파일 & satisfy 표현력

- **기본 프로파일: OWL 2 EL** — 분류·포섭·∃·conjunction·transitive·disjoint(⊥). satisfy의 **정성 subsumption**에 충분.
- **satisfy에 필요한 추가 표현력**(요구=증상 부재 `RB ≡ ¬∃exhibits.Symptom`, 수치 범위)은 **OWL을 DL로 키우지 않고 SHACL(CWA) + 구간 비교기로 흡수** → "EL + SHACL 이중화" 원칙 유지.
- (옵션) 순수 데이터타입 구간 subsumption을 OWL 안에서 다루고 싶으면 해당 공리만 **국소 DL 조각**으로 허용 가능(에스컬레이션). 기본은 EL+SHACL.

---

## 5. M1 — 와이퍼 도메인 (확대)

### 5.1 개념 (punning: `a spmm:… , owl:Class`)
`WiperBlade ⊑ PartType` · `WiperArm ⊑ Component` · `Rubber`·`Silicone ⊑ Material`(Silicone: 저온탄성) · `MidSizeSUV`·`CompactSedan` a `VehicleType`(maxSafeLengthMm 599/550) · `Winter` a `EnvCondition` · `Noise`·`TipChatter ⊑ Symptom`.

### 5.2 확대 지식문장 — 증상-인과(유지) + 요구-설계(신규)

**A. 증상-인과 문장 (S1~S6, 유지)** — `causes`/`mitigates`/`aggravates`/`conditionedOn`으로 표현

| # | 문장 | 인과 표현 |
|---|------|-----------|
| S1 | 겨울철 고무 경도↑ → 소음 | (Rubber∧Winter) `causes` Noise |
| S2 | 실리콘 저온 탄성 → 소음 해소 | Silicone `mitigates` Noise |
| S3 | SUV 길이 ≥600 → 떨림 | (SUV∧length≥600) `causes` TipChatter |
| S4 | 스프링 <10N → 떨림 악화 | (springN<10) `aggravates` TipChatter |
| S5 | 세단 550까지 떨림 없음 | (Sedan∧length≤550) `mitigates` TipChatter |
| S6 | 단순 암형상 → 떨림 악화 | (armShape=simple) `aggravates` TipChatter |

**B. 요구-설계 만족 문장 (신규 확대)** — RequiredBehavior / DesignedBehavior / satisfy
> ※ RB·DB는 도메인 지식(M1)이 아니라 **프로젝트 데이터(M2)**. 아래 R1·R2·D1은 "예시 프로젝트"의 요구·설계이며, 실제로는 엔지니어가 프로젝트별로 자연어 입력한다.

| # | 유형 | 문장 |
|---|------|------|
| R1 | RequiredBehavior | 겨울철 운용 와이퍼는 **소음이 없어야 한다** (`RB_Winter ≡ ¬∃exhibits.Noise`). |
| R2 | RequiredBehavior | 블레이드는 대상 차종에서 **끝단 떨림이 없어야 한다** (`RB_NoChatter ≡ ¬∃exhibits.TipChatter`). |
| D1 | 설계원칙(satisfy) | **실리콘 ∧ 길이 ≤ 차종 maxSafe ∧ 스프링 ≥10N ∧ 복합 암형상** 설계는 R1·R2를 **만족한다**(`DB ⊑ RB_Winter ⊓ RB_NoChatter`). |

> 6문장은 그대로 두고(증상-인과), 그 위에 R1·R2(요구)와 D1(설계 만족 원칙)을 얹어 satisfy가 6문장 규칙을 근거로 판정한다.

### 5.3 satisfy 워크드 예시

| 설계(DB) | (1)정성 | (2)수치 | (3)무증상 | 판정 |
|----------|:--:|:--:|:--:|------|
| 실리콘·550·12N·complex·세단 | ✔(실리콘⊑저소음) | ✔(550≤550, 12≥10) | ✔(S2·S5) | **satisfy ✔** (근거 S2·S5·D1) |
| 고무·600·8N·simple·SUV | ✘ | ✘(600>599, 8<10) | ✘(S1·S3·S4·S6) | **✘** — 위반 S1·S3·S4·S6 + 대안(실리콘/≤599/≥10N/complex) |

---

## 6. OWL 활용 지도

| OWL/규칙 기능 | 적용 지점 | 예 |
|---------------|-----------|-----|
| **punning(clabject)** | M1 개념=개체+클래스 | `dom:WiperBlade a dom:PartType, owl:Class` |
| **disjoint** | M0 4범주 + Behavior 3종 | `AllDisjointClasses(Entity Form Behavior Attribute)` |
| **∃ someValuesFrom** | 필수속성·요구정의 | `WiperBlade ⊑ ∃hasMaterial.Material` |
| **transitive** | has_subbehavior | 거동 위계 도출 |
| **subsumption(satisfy)** | 정성 DB⊑RB | 설계 만족 증명(핵심) |
| **인과 상위어(M0-ext)** | causes/mitigates/aggravates/conditionedOn | 증상 유발/해소 표현·FMEA |
| **SHACL(CWA)+구간비교기** | 수치·기수·단위·무증상 | 길이≤maxSafe, 스프링≥10N |
| **SPARQL/규칙** | DesignRule·Q&A Layer A | 규칙 조회·영향분석 |

---

## 7. 저장모델 = RDF / SHACL ★ 변경

- **RDF triplestore 主**(rdflib 기반, 필요 시 경량 triplestore). **Neo4j 미채택** — 현 규모에서 LPG 이중저장의 복잡도가 이득보다 큼.
- **SHACL(pySHACL)** 이 검증·게이트. **OWL 추론(owlready2/HermiT/ELK)** 은 같은 RDF 그래프 위에서 직접 동작(별도 투영층 불필요).
- **지식맵** = RDF에 대한 SPARQL 질의 결과를 그래프 뷰(Cytoscape 등)로 렌더. 층/증상/문장 필터도 SPARQL로.
- **명세·공리·SHACL·규칙**: TTL 파일 + (메타는) 경량 저장. 단일 RDF 데이터 모델로 정합성↑.
- **아키텍처 함의**: 통합 백본은 dev-system의 프론트·기능 셸을 유지하되, **데이터/지식 계층은 RDF 네이티브(pkms-web의 rdflib/pySHACL 코어 계승)** 로 단일화한다.

---

## 8. TTL 스케치 (발췌, v0.2)

```turtle
@prefix spmm: <http://ex.org/spmm#> .   @prefix ext: <http://ex.org/spmm-ext#> .
@prefix dom:  <http://ex.org/domain#> . @prefix sh: <http://www.w3.org/ns/shacl#> .

# ── M0-core (SPMM FBS) ──
spmm:DesignedBehavior rdfs:subClassOf spmm:Behavior .
spmm:RequiredBehavior rdfs:subClassOf spmm:Behavior .
spmm:satisfy_beh_required a owl:ObjectProperty ;
    rdfs:domain spmm:DesignedBehavior ; rdfs:range spmm:RequiredBehavior .

# ── M0-ext (증상·인과·구조 상위어) ──
ext:FailureBehavior rdfs:subClassOf spmm:Behavior .
ext:Symptom rdfs:subClassOf ext:FailureBehavior .
ext:EnvCondition rdfs:subClassOf spmm:Attribute .
ext:PartType rdfs:subClassOf spmm:Artifact .
ext:causes    a owl:ObjectProperty ; rdfs:range ext:FailureBehavior .
ext:mitigates a owl:ObjectProperty ; rdfs:range ext:FailureBehavior .

# ── M1 (와이퍼, punning) + 요구/설계 ──
dom:WiperBlade a ext:PartType, owl:Class ;
    rdfs:subClassOf [ a owl:Restriction ;
        owl:onProperty dom:hasMaterial ; owl:someValuesFrom dom:Material ] .
dom:RB_NoChatter a spmm:RequiredBehavior ;
    owl:equivalentClass [ a owl:Class ; owl:complementOf
        [ a owl:Restriction ; owl:onProperty dom:exhibits ; owl:someValuesFrom dom:TipChatter ] ] .

# ── M2 인스턴스 (검증 대상) ──
eng:Blade-001 a dom:WiperBlade ; dom:lengthMm 600 ;
    dom:hasMaterial dom:Rubber ; dom:mountedOn dom:MidSizeSUV ; dom:springN 8 .
```

```turtle
# ── SHACL 수치 게이트 (ChatterRule; CWA) ──
dom:ChatterShape a sh:NodeShape ; sh:targetClass dom:WiperBlade ;
  sh:sparql [ sh:message "길이 > 차종 안전길이 → 떨림(S3/S5)" ;
    sh:select """SELECT $this WHERE {
      $this dom:lengthMm ?l ; dom:mountedOn ?v . ?v dom:maxSafeLengthMm ?m .
      FILTER(?l > ?m) }""" ] .
# 구간 비교기(서비스): satisfy 시 length∈[0,maxSafe], springN≥10 등 구간 포함을 결정론적으로 판정
```

---

## 9. 변경 요약 (v0.1 → v0.2) & 다음 단계

- **[변경]** M1-mid 구조·증상 슬라이스 → **M0-ext 상위어로 승격**(증상·인과·제품구조 확장).
- **[변경]** 저장모델 **Neo4j LPG → RDF/SHACL 단일화**.
- **[추가]** satisfy **수치 보완**(SHACL 게이트 + 구간 비교기) 명시, 3단계 결합.
- **[추가]** 와이퍼 문장 **확대**(R1·R2 요구 + D1 설계 만족).
- **[유지]** punning · satisfy subsumption · OWL EL+SHACL 이중화 · 목표/비목표.
- **다음(Phase 2 이후는 유지)**; 본 변경은 Phase 3(기능구조도 §C3 저장)·Phase 5(열린항목)에 반영.
