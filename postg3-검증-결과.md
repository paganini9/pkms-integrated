# 포스트-g3 실 검증 결과 (③)

> **게이트 아님 — 관찰 보고.** 목적: provider 정책 확정 + ④⑤ 스코핑 + 브리틀니스 노출.
> 스택: full(`INCLUDE_ML=true EMBEDDING_PROVIDER=local`) — frontend + bff(Solar/Claude 실키) + knowledge(temurin JRE + MiniLM 384).
> `/health`: status=ok · reasoner=ok(HermiT) · embedding_provider=local · 시드 347 트리플 · 벡터 6문장.
> 문장 세트: 신규 어휘 13문장(K1~K5 인과-단언 / R1~R8 요구·RB). 2026-07-12 · 브랜치 `chore/postg3-validation`.
> **발견한 결함은 이 브랜치에서 고치지 않았다** — 전부 §7 브리틀니스 로그로 남긴다.

## 0. 한 줄 결론

신규 어휘 13문장을 실제로 태운 결과, **저작 26회 시도(13문장×2 provider) 중 저장 성공은 1건**이고
그 1건마저 요구문장을 지식으로 오저장한 것이다. 실패는 LLM 품질이 아니라 **파이프라인 구조**에서 왔다:
접지·타입·IRI·규칙 세 지점이 각각 독립적으로 저작을 막는다. **A/B 마진은 Claude 우세로 명확** —
저작 기본=Claude 정책은 **유지**한다(T-89의 "Solar==Claude" 는 6문장 in-domain 한정 관찰이었다).

| 저장 시도 결과 (26회) | 건수 |
|---|---:|
| 201 저장 성공 | **1** (R7·Solar — 요구문장을 지식으로 오저장, 관계 0건) |
| 409 GUARDRAIL_BLOCKED (명세 위반) | 20 |
| **500 INTERNAL (크래시)** | **4** |
| 422 VALIDATION_ERROR (Solar 스키마 위반) | 1 |

---

## (a) Solar vs Claude A/B 대조표 — 13문장 전량

각 provider 추출안을 **같은 결정론 게이트**(`/extraction/validate`)에 그대로 태웠다.

| 지표 | Solar | Claude | 마진 |
|---|:--:|:--:|---|
| **복합어 분해** (고무 블레이드·블레이드 프레임·와이퍼 암 커넥터 등 5곳) | **2/5** | **5/5** | **Claude +3** |
| 대상 증상 포착 | 12/13 | **13/13** | Claude +1 |
| 조건 앵커 정확 (conditionedOn 주어=증상) | 5 | **7** | Claude +2 |
| **유령 참조** (관계가 개념목록에 없는 라벨을 지목) | **6건** | **0건** | Claude 우세 |
| **문장에 없는 "고무" 발명** (few-shot 반향) | **3건** | **0건** | Claude 우세 |
| 차단성 위반(severity=violation) 총량 | 28 | **15** | Claude 절반 |
| 스키마 위반(빈 object → 422) | 1 | 0 | — |

문장별 원자료: `scratchpad/results/ab.json`. 대표 대비:

- **K4** "염화칼슘에 반복 노출되면 블레이드 프레임에 부식이 발생한다."
  - Solar: `블레이드 프레임`(원자 복합어) · `블레이드 프레임 -hasMaterial-> 염화칼슘` (**재질 오귀속**)
  - Claude: `블레이드`+`프레임` 분해 · `염화칼슘 -causes-> 부식` · `부식 -conditionedOn-> 반복 노출` (기전·조건·증상 정합)
- **R8** Solar 는 `차량용 와이퍼 암 커넥터` 를 한 덩어리로, Claude 는 `와이퍼 암`+`커넥터`+`차량` 으로 분해하고
  `견고한 체결 -mitigates-> 주행 중 이탈` 로 **요구의 방향성(완화)** 까지 잡았다.
- **R7** Solar 는 관계를 하나도 못 만들고 개념 3개만 냈다 → 위반 0 → **201 저장됨**(§7-B4).

**RB(M2) 파싱 A/B** (`AI_AUTHORING_PROVIDER` 전환 재기동으로 측정):

| | Claude | Solar |
|---|---|---|
| 초안 생성 | 과생성 (문장당 2~8건, 증상이 아니라 문장 형태의 서술) | 과소생성 (R4~R8 **0건 무응답**) |
| 최종 `requirements` | **0/8** | **0/8** |

→ RB 병목은 모델이 아니라 **하드코딩된 2증상 맵**이다(§7-A2). 여기서는 A/B 마진이 무의미하다.

### provider 정책 결론 (확정)

**저작=Claude 유지.** 신규 어휘에서 Claude 는 복합어 분해 5/5·유령참조 0·환각 0 으로 Solar 를 확실히 앞선다.
Solar 되돌림 근거는 **성립하지 않는다**. 단, 저작 성공률이 구조적 결함에 눌려 있어(1/26) **이 마진은 아직 값을 못 낸다** —
④⑤ 로 구조를 고친 뒤 재측정하면 마진이 더 벌어질 수도, 무의미해질 수도 있다(그때 재판정).
Q&A=Solar 는 이번 관찰 범위에서 문제 없음(§g 참조).

---

## (b) OOV 동작 — 후보·거부·승인 편입

21개 신규 라벨을 `/oov/triage` 에 태웠다(`results/oov.json`).

**B1. "정당한 거부"가 한 번도 발화하지 않는다 — 21/21 전부 `synonym_variant`.**
트리아지 분기가 `candidates.length > 0 ? synonym_variant : out_of_scope` 인데, 임베딩 후보는 **항상 top-k 를 채워 돌려준다**
(점수 하한 없음). 즉 `out_of_scope`(범위 밖 = 정당한 거부)는 **도달 불가능한 죽은 가지**다.
도메인 밖인 "타이어"조차 `Rubber(0.68)` 후보를 받고 "altLabel 편입 제안" 이 붙는다.

**B2. 후보 품질이 위험하다** — 표기 유사도에 끌려간다:

| 라벨 | 1순위 후보 | 점수 | 판정 |
|---|---|--:|---|
| **경화** | **경도**(Hardness) | **0.987** | ❌ 의미 무관(경화≠경도). 승인 시 온톨로지 오염 |
| **오존** | **경도**(Hardness) | **0.922** | ❌ 완전 무관 |
| 부식 | 경도 | 0.94 | ❌ |
| 워셔액 | 경도 | 0.95 | ❌ |
| 와이퍼 블레이드 | WiperBlade | 1.0 (lexical) | ✅ 유일하게 옳음 |

관리자가 UI 카드의 1순위 제안을 그대로 승인하면 **"오존"이 Hardness 의 altLabel** 이 된다 — 접지가 조용히 오염된다.
`admin_proposal.status` 는 문자 그대로 `"stub"` 이고 제안 큐는 없다.

**B3. 승인→편입 경로는 실제로 작동한다(유일하게 설계대로 돈 부분).**
`/upper-ontology/classes`(add Ozone·Crack) → `/oov/approve`(altLabel 오존·균열) 후 재검증하면
`unknown_concept` 경고가 사라지고 `oov/triage` 가 `in_domain=true` 로 바뀐다. 오버레이 TTL 에 영속된다.
다만 도달 경로가 어긋나 있다(§7-A3): 승인 API 가 **BFF 에 없어서 404** — 지식서비스(:8000)를 직접 때려야만 승인된다.

**B4. 접지 fail-closed 는 Q&A 에만 성립한다.** 저작 저장 경로에서 `unknown_concept` 는 `severity=warning` 이라
**도메인 밖 개념이 KG 에 그대로 들어간다**(실증: 라벨 "타이어" → 201 저장). 차단된 20건은 OOV 때문이 아니라
타입·range 위반 때문이었다. "우회 9/9 차단"은 Q&A 가드레일의 성질이지 저작 저장의 성질이 아니다.

---

## (c) 인과 reification (T-91) — 런타임에서 한 번도 실행되지 않는다

**`CausationReifier` 는 데드 코드다.** `reify_relations`·`validate_causation` 을 호출하는 곳이
**유닛 테스트(`test_t91_causation.py`)뿐**이다. 실 경로 `/validate/shacl` 는 `SpecValidator.validate()` 만 부르고
(`knowledge/reasoning/routes.py:69`), `kg/save` 도 Causation 을 만들지 않는다.

실증: K2 를 완전 접지 상태로 저장(201·S11)한 뒤
`SELECT ?s WHERE { ?s a ext:Causation }` → **0 행**. 저장된 것은 평면 트리플뿐이다.

즉 T-91 이 없앴다고 한 이항 우회(바인딩 소실·PartType-conditionedOn 도메인 위반)는 **런타임에 그대로 남아 있다.**
이번 세트에서도 그 병이 재발했다 — K3 Solar `경화 -conditionedOn-> 영하 40도`(경화=Attribute → 도메인 위반),
R2 Solar `와이퍼 -conditionedOn-> 유리 표면`(부품 앵커). 조건 앵커 정확도가 Solar 5/13·Claude 7/13 에 그친 이유다.

---

## (d) M1 / M2 라우팅 — 시스템은 요구와 지식을 구분하지 않는다

**D1. 구분 장치가 없다.** M1(SmartInput)/M2(RB)는 **사용자가 어느 화면에 넣느냐**로만 갈린다.
분류기도, 경고도, 힌트도 없다. R1·R5 를 일부러 M1 스트림에 넣었더니 그대로 **지식으로 추출**했다:

```
R1 "블레이드는 고속 주행 중 들뜸 현상이 발생하지 않아야 한다."  → M1 SmartInput
  concept: 블레이드 / 고속 주행 / 들뜸
  relation: 블레이드 -causes-> 들뜸          ← 요구의 부정이 사라지고 인과 단언으로 뒤집힘
  validation: conforms=true                  ← 승인 버튼이 열린다
```

**요구("들뜸이 없어야 한다")가 지식("블레이드가 들뜸을 유발한다")으로 의미가 반전된 채 검증을 통과한다.**
저장까지 갔다면 KG 는 요구와 정반대의 인과를 갖게 된다(공백 라벨 크래시가 우연히 막았을 뿐이다 — §7-B1).
R7 은 실제로 **저장에 성공**했고(S7·polarity=`cause`), 요구문장이 `소음` 카테고리 지식으로 들어갔다.

**D2. 반대 방향(M2에 지식 투입)은 미측정** — RB 경로가 애초에 0건을 내므로 관찰 가치가 없었다.

---

## (e) 부정 / 증상부재 (RB=증상부재, 열린항목 #5) — 표현할 방법이 없다

8개 요구는 전부 **must-not**("~하지 않아야 한다")인데, 파이프라인 어디에도 부정을 담을 자리가 없다.

- **추출 스키마**: `predicate` 는 `causes·mitigates·aggravates·conditionedOn·hasMaterial·has_part·mountedOn·operatesIn` 8종뿐.
  **부정·금지·부재 술어가 없다.** 그래서 LLM 은 부정을 버리고 긍정 인과로 평탄화한다(§d).
  Claude 가 R8 에서 `견고한 체결 -mitigates-> 주행 중 이탈` 로 낸 게 **현재 스키마가 낼 수 있는 최선의 근사**다.
- **저장 모델**: `polarity` 는 `cause|mitigate|aggravate` — must-not 은 전부 `cause` 로 눌린다.
- **RB 모델**: `forbids_symptom`(금지 증상) 필드가 **유일한 부정 표현**인데, 알려진 증상 2종(Noise·TipChatter)에만
  매핑되므로 신규 증상(들뜸·균열·부식·이탈…)은 전부 `unknown_symptoms` 로 떨어진다 → **요구 0건**.
- **satisfy**: `symptom_free` 단계가 "증상부재"를 판정하는 유일한 기계장치인데, 판정 대상은 **컴파일된 규칙이 만든 증상**뿐이다.

→ 열린항목 #5 는 여전히 **열려 있다**. 부정 술어(또는 RequiredBehavior 의 1급 모델링) 없이는
R1~R8 중 **어느 것도 요구로 표현될 수 없다**. ④⑤ 의 1순위 후보다.

---

## (f) 전체 루프 (플래그십) — 닫히지 않는다

K2(오존→균열) 저작 → OOV 승인 → R5 저작 → 설계 → satisfy 를 끝까지 밀었다(`results/flagship*.json`).

| 단계 | 결과 |
|---|---|
| 1. K2 추출 (Claude) | ✅ 오존 노출·블레이드·고무·균열 + causes/conditionedOn |
| 2. 검증(편입 전) | ⚠️ `unknown_concept` 오존 노출·균열 + **`shacl_constraint` 블레이드**(차단) |
| 3. 상위 온톨로지 add (Ozone·Crack) | ✅ 200 · 오버레이 TTL 영속 — 단 **ext: 네임스페이스·영문 라벨**로 생성 |
| 4. OOV 승인 (altLabel 오존·균열) | ⚠️ **BFF 404** (표면 없음) → 지식서비스 직접 호출로만 성공. 로컬네임은 422, **전체 IRI 필수** |
| 5. 재검증 | ✅ OOV 경고 소멸 · `in_domain=true` — **어휘 진화는 실제로 작동한다** |
| 6. 저장 | ❌ **500** — 남은 위반(블레이드 타입)을 HITL 로 고쳐 violations=0 을 만들어도 **여전히 500**(공백 라벨 IRI 크래시) |
| 6′. 우회 저장 (`오존 노출`→`오존`) | ✅ 201 (S11) — 공백을 없애야만 저장된다 |
| 7. 파생 규칙 | ❌ `id="소음Rule"` · `about_symptom=null` · `causal_edges: 소음Rule -causes-> **소음**` — **증상이 균열이 아니라 프로젝트 카테고리로 오귀속** |
| 8. `/rules` | ❌ 여전히 **시드 5개 규칙뿐**. S11 은 규칙이 되지 않는다 |
| 9. satisfy | ❌ 새 지식 **반영 0**. 판정은 시드 규칙(S1·S3·S6)만으로 나온다 |
| 10. 설계에 오존 표현 | ❌ Design 스키마는 `material·vehicle·length_mm·spring_n·arm_shape·env(Winter)` 뿐. `ozone_ppm` 을 넣으면 **조용히 버려진다**(zod 비-strict) |

**루프는 저작~편입까지만 돈다. 저작된 지식이 판정에 도달하는 다리가 없다.**
규칙은 `rules.ttl`(정적 시드)에서만 컴파일되고, 저장 응답의 `derived` 는 **영속되지 않는 일회용 투영**이다.
설계 스키마가 고정 필드라 새 환경조건(오존·자외선·염화칼슘)은 애초에 입력할 수도 없다.
→ **④⑤ 의 핵심 과제**: 저작→규칙→게이트→판정의 연결(그리고 설계 표현의 개방).

---

## (g) 안전 — 유지됨

| 프로브 | 결과 |
|---|---|
| 도메인 밖 Q&A (자전거 브레이크 / 타이어 공기압) | ✅ `insufficient_evidence=true` · "명세 근거 없음" · sources 0 · llm_answer=null (**fail-closed**) |
| 위조 초안 저장 (range 위반) | ✅ **409 GUARDRAIL_BLOCKED** (서버 재검증) |
| 도메인 밖 개념 저장 (타이어→마모) | ⚠️ 차단 아님 — `unknown_concept`=warning 이라 **저장 허용**(§7-B4). 우연히 500 으로 죽었을 뿐 |
| in-domain Q&A ("겨울철 와이퍼 소음") | ⚠️ **insufficient** 반환 — 과차단 의심(§7-C1) |

Q&A 가드레일(우회·환각)은 g3 수준을 유지한다. 다만 **저작 저장 경로에는 도메인 게이트가 없다**는 점이
이번에 처음 실증됐다(g3 회귀셋은 Q&A 우회만 쏘았다).

---

## (h) 브리틀니스 로그 — 무엇이 깨졌나

> 전부 **이 브랜치에서 고치지 않았다.** ④⑤ 스코핑 입력.

### A. 구조 결함 (설계를 건드려야 함)

| # | 결함 | 증거 | 영향 |
|---|---|---|---|
| **A1** | **저작→규칙→satisfy 다리 없음.** 규칙은 `rules.ttl` 시드에서만 컴파일. 저장 응답의 `derived` 는 비영속 투영 | S11 저장 후 `/rules` 5건 불변, satisfy 반영 0 | **치명** — 지식을 넣어도 설계 판정이 바뀌지 않는다. 제품 명제의 핵심 |
| **A2** | **RB 증상 맵이 하드코딩 2종**(`misc.ts:15 KNOWN_SYMPTOM` = Noise·TipChatter) | R1~R8 **requirements 0/8**, 전량 unknown_symptoms (Claude·Solar 동일) | **치명** — 신규 요구를 하나도 등록할 수 없다 |
| **A3** | **부정/증상부재 표현 부재.** 술어 8종에 부정 없음 · `polarity` 3종에 must-not 없음 | R1 → `블레이드 -causes-> 들뜸`(의미 반전) conforms=true | **치명** — 요구가 정반대 지식으로 저장될 수 있다. 열린항목 #5 |
| **A4** | **M1/M2 구분 장치 없음** — 화면 선택이 유일한 분기 | R1·R5 를 M1 에 넣으면 지식으로 추출·검증 통과 | 높음 — 사용자 실수가 KG 오염으로 직결 |
| **A5** | **검증기가 온톨로지 타입 대신 LLM 이 붙인 타입으로 판정.** `WiperBlade ⊑ ext:PartType` 인데 두 provider 모두 `Component` 로 타입 → `hasMaterial` 도메인 위반 → 차단 | K2·K3·K4·R1… 20건 중 다수의 409 원인 | **높음** — 접지된 개념인데도 저장 불가. "고무 블레이드" 지식은 현재 **어떤 provider 로도** 저장 못 함 |
| **A6** | **설계 스키마 고정** — 새 환경조건(오존·자외선·염화칼슘·온도)을 표현할 필드 없음. 미지 필드는 zod 가 조용히 제거 | `ozone_ppm` 투입 → 무시, `satisfies=null` | 높음 — 새 지식이 판정에 닿을 입구가 없다 |
| **A7** | **T-91 인과 reification 이 런타임 미배선**(데드 코드) | Causation 노드 0행 · 호출부가 테스트뿐 | 높음 — 이항 우회 병(도메인 위반·바인딩 소실)이 그대로 재발 |
| **A8** | **OOV `out_of_scope`(정당한 거부) 도달 불가** — 임베딩이 항상 top-k 를 채움, 점수 하한 없음 | 21/21 `synonym_variant`, 타이어조차 후보 부여 | 높음 — 거부 경로가 없으면 트리아지는 승인 편향 |
| **A9** | **OOV 후보 품질** — 표기 유사도 오탐 (경화→경도 0.99, 오존→경도 0.92) | §b 표 | 높음 — 1순위 승인 시 접지 오염 |

### B. 구현 결함 (국소 수정 가능)

| # | 결함 | 증거 | 영향 |
|---|---|---|---|
| **B1** | **공백 포함 라벨 → IRI 생성 크래시 500.** `oxigraph.py:172` 가 미해석 라벨을 그대로 IRI 로 민팅 (`ValueError: Invalid IRI code point ' '`) | "고속 주행"·"주행 중"·"외부 화학 물질 노출" → 500. 라벨 이등분으로 재현 확정 | **치명** — 완전 접지·violations 0 초안도 저장 불가. 계약 위반(500 INTERNAL) |
| **B2** | **파생 규칙 증상 오귀속** — `about_symptom=null`, `causal_edges` 가 프로젝트 카테고리(`소음`)를 증상으로 삼음. 규칙 id 가 문장별이 아니라 **카테고리별**(`소음Rule` 충돌) | S7·S11 둘 다 `소음Rule` | 높음 |
| **B3** | **OOV 승인 표면이 BFF 에 없음** — `/oov/approve` 404. 지식서비스 직접 호출만 가능(경계 원칙 위반). 로컬네임 거부(422) → 전체 IRI 필수인데 UI 는 IRI 를 모름 | §f-4 | 높음 — UI 에서 승인 불가 = 거버넌스 루프 미완 |
| **B4** | **저작 저장에 도메인 게이트 없음** — `unknown_concept`=warning | 라벨 "타이어" → 201 저장 | 중간 — 정책 판단 필요(warning 이 의도라면 문서화) |
| **B5** | **신설 클래스가 ext: 네임스페이스·영문 라벨로 생성** — `edit()` 이 `rdfs:label` 에 **id 를 넣고** 사용자 label 을 버림 | Ozone/Crack → `ext:Ozone rdfs:label "Ozone"` | 중간 — 한글 표면어는 별도 altLabel 승인 2단계 필요 |
| **B6** | **Solar 스키마 위반** — 빈 `object` 관계 방출 → BFF 422 | K1 solar | 낮음(Claude 정책이면 노출 감소) |

### C. 관찰 (재현 필요)

| # | 관찰 |
|---|---|
| **C1** | in-domain Q&A "겨울철에 와이퍼 소음이 왜 생기나요?" 가 `insufficient_evidence=true` 로 과차단됐다(local MiniLM·시드 6문장·scope 소음/떨림). g3 회귀셋의 rag-verified 는 통과했으므로 **질의 표현 의존**일 수 있다. 재현·격리 필요 |
| **C2** | HITL 거부 빈도 = 저작 시도의 **96%**(25/26 비저장). 사용자 관점에서 "무엇을 고쳐야 승인되는가"에 대한 안내는 위반 메시지뿐이고, A5 처럼 **사용자가 고칠 수 없는** 위반이 섞여 있다 |

---

## 4. ④⑤ 스코핑 제안 (근거 기반)

우선순위는 "제품 명제를 되살리는 것"부터다.

1. **A1 저작→규칙→판정 연결** (+ A6 설계 표현 개방) — 이게 없으면 나머지는 장식이다.
2. **A3 부정/증상부재 1급 모델링** (+ A2 RB 증상 맵 제거) — 요구를 요구로 저장할 수 있게.
3. **A5 타입 판정을 온톨로지 소속으로** (+ B1 IRI 민팅) — 저작 성공률을 0 에서 끌어올리는 최소 수술.
4. **A7 T-91 배선** · **A8/A9 OOV 거부·후보 품질** · **B3 승인 표면** — 거버넌스 루프 완성.
5. **A4 M1/M2 구분** — 오염 예방.

provider 정책은 **저작=Claude 유지**(A/B 마진 명확). 구조 수술 뒤 재측정한다.

---

## 5. 재현 방법

```bash
INCLUDE_ML=true EMBEDDING_PROVIDER=local docker compose up --build -d
python _coordination/qa/run_postg3_probe.py all      # ab·rb·route·flagship·safety
python _coordination/qa/run_postg3_probe.py "oov:들뜸,오존,경화,타이어,..."
```
원자료: `docs/postg3-원자료/{ab,rb,rb_solar,route,oov,flagship,flagship_loop,safety}.json`.
프로브가 스토어에 넣은 문장(S7~S11)은 `/kg/delete` 로 정리했다(시드 6문장 복원 확인).
3화면 클릭스루 스크린샷은 재현님 수동 병행.
