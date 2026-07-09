# PKMS 온톨로지 백본 — TTL 구체화 + reasoner satisfy 실증 결과

> 작성일 2026-07-09 · Phase 1 v0.2 백본을 실제 TTL·reasoner로 실행 검증.
> 스택: rdflib 7 · owlrl(OWL RL) · owlready2+**HermiT**(DL) · pySHACL(SHACL) — 전부 키 없이 로컬 구동.

---

## 1. 산출 파일

```
ttl-demo/
├── ontology/
│   ├── m0.ttl            # M0-core(SPMM FBS) + M0-ext(증상·인과·제품구조 상위어)
│   ├── m1_wiper.ttl      # 와이퍼 도메인(punning) + 6문장 + 규칙 + 요구/설계 거동(RB)
│   ├── shapes.ttl        # SHACL 게이트 4종(S1·S3·S4·S6) — 6문장의 CWA 구현
│   └── m2_instances.ttl  # 설계 인스턴스 2종(good/bad)
├── satisfy_demo.py       # OWL 추론 + 일관성 + SHACL + satisfy 3단계 결합
└── satisfy_run_output.txt
```

실행: `cd ttl-demo && python3 satisfy_demo.py`

---

## 2. 백본 결정 ↔ 실행으로 확인된 것

| Phase 1 v0.2 결정 | TTL/코드에서 | 실행 결과 |
|-------------------|--------------|-----------|
| SPMM FBS + 증상·인과 상위 확장 | m0.ttl (M0-core+ext) | 분류 사슬 WiperBlade⊑PartType⊑Artifact⊑Entity 추론 ✔ |
| OWL2 punning 유지 | `dom:Rubber a owl:Class, spmm:Material` | Class이자 개체로 동시 성립 ✔ |
| has_subbehavior transitive | m0.ttl TransitiveProperty | 와이핑→접촉 이행 도출 ✔ |
| disjoint 일관성 | AllDisjointClasses | 위반 0(일관성 OK), 고의 모순은 포착 ✔ |
| EL+SHACL 이중화 | pySHACL 게이트 | 6문장을 CWA 규칙으로 실행 ✔ |
| **satisfy(DB⊑RB) 유지** | satisfy 3단계 | good ✅ / bad ⛔ |
| **수치 보완(구간 비교기)** | interval_comparator | 550≤550·12≥10 ✔ / 600≤599·8≥10 ✘ |
| 6문장 유지+요구-설계 확대 | S1~S6 + RB_Winter/RB_NoChatter | 위반 근거를 문장 번호로 역추적 ✔ |
| DL 일관성(정통 reasoner) | owlready2+HermiT | HermiT 일관성 통과 ✔ |

---

## 3. satisfy 3단계 결합 (핵심)

```
satisfy(DB, RB)  ⟺  (1) 정성 subsumption ∧ (2) 수치 게이트·구간 비교기 ∧ (3) 무증상 규칙
```
- **(1) 정성**: 재질·형상 등 비수치 포섭(OWL). 실리콘 ⊑ 저소음(S2).
- **(2) 수치**: SHACL(CWA) + 경량 **구간 비교기**로 길이·압력 판정. subsumption만으로 어려운 수치를 결정론적으로 보완.
- **(3) 무증상**: 6문장 DesignRule을 SHACL로 실행 → RB가 금지한 증상 유발 여부.
- 셋 다 통과 → satisfy ✔. 하나라도 실패 → ⛔ + 위반 문장·값·허용 대안.

---

## 4. 실행 로그 (원문)

```
로드: onto 218 triples · data 24 triples · shapes 32 triples

==== (A) OWL RL 추론 — 분류 · 이행 · punning ====
  eng:Blade_good 추론된 타입: ['Artifact', 'Entity', 'PartType', 'WiperBlade']
    → WiperBlade ⊑ PartType ⊑ Artifact ⊑ Entity 분류 사슬: 성립 ✔
  has_subbehavior 이행: 와이핑 →(추론)→ 접촉 거동 : 도출 ✔
  punning: dom:Rubber 가 owl:Class=True 이면서 spmm:Material 개체=True : 성립 ✔

==== (B) 일관성 · disjoint 검사 ====
  현 온톨로지 disjoint 위반: 0 건 → 일관성 OK ✔
  고의 모순(eng:Clash 를 Entity∧Behavior 로): disjoint 위반 1 건 감지 → reasoner 가 모순 포착 ✔
  [HermiT/DL] 온톨로지 일관성 검사 통과 ✔ (Java HermiT 실행)

==== (C) SHACL 게이트 (pySHACL) — 6문장 규칙을 CWA 로 실행 ====
  전체 conforms = False  (위반 focus 노드 1개)
   · 설계 A (고무·600·8N·simple·SUV) — 위반 4건
       [S1] 겨울철 운용 + 고무 재질 → 소음 발생
       [S3] 블레이드 길이가 차종 안전길이 초과 → 끝단 떨림
       [S4] 암 스프링 압력 부족(<10N) → 끝단 떨림 악화
       [S6] 단순 암형상 → 압력 편차↑ → 끝단 떨림 악화

==== (D) satisfy 판정 ====
▶ 설계 B (실리콘·550·12N·complex·세단)
  (1) 정성 subsumption : ✔  — 재질 실리콘 ⊑ 저소음(S2)
  (2) 수치 게이트·구간 비교기:
        ✔ 길이 length ≤ maxSafe  (550 ≤ 550)
        ✔ 스프링 springN ≥ 10  (12 ≥ 10)
  (3) 무증상 규칙: 유발 증상 없음
  ── satisfy 판정: ✅ 만족 (DB ⊑ RB_Winter ⊓ RB_NoChatter)

▶ 설계 A (고무·600·8N·simple·SUV)
  (1) 정성 subsumption : ✘  — 재질 고무 ∧ 겨울 → 소음(S1)
  (2) 수치 게이트·구간 비교기:
        ✘ 길이 length ≤ maxSafe  (600 ≤ 599)
        ✘ 스프링 springN ≥ 10  (8 ≥ 10)
  (3) 무증상 규칙: 유발 증상 → 끝단 떨림[S3·S4·S6], 소음[S1]
  ── satisfy 판정: ⛔ 불만족
       위반 요구: 겨울 저소음 — 금지 증상 '소음' (근거 S1)
       위반 요구: 끝단 떨림 없음 — 금지 증상 '끝단 떨림' (근거 S3·S4·S6)
       허용 대안: 재질→실리콘(S2), 길이→안전길이 이내(S5), 스프링→≥10N, 암형상→complex
```

---

## 5. 관찰 · 다음 단계

- **환각가드 데모로 직결**: LLM이 "고무·600mm 가능"이라고 답해도, reasoner가 S1·S3·S4·S6 근거로 ⛔ + 대안을 결정론적으로 제시 → S-05 환각비교 모드의 백엔드 그대로.
- **satisfy 정통성**: 정성 포섭은 EL/HermiT, 수치는 SHACL+구간 비교기로 분담해 "EL+SHACL 이중화"를 지키면서 satisfy 표현력 확보 — v0.2 결정과 일치.
- **다음**: (a) RB/DB를 OWL 정의 클래스로 더 정교화(요구=증상 부재를 owl:complementOf로), (b) SHACL 위반 설명(xpSHACL식) 자연어화, (c) 이 엔진을 백엔드 `/satisfy` API로 감싸 S-03 화면과 연결.
