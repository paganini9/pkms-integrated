# ③′ 소형 재측정 결과 — 1단계 후 저작 루프 회복 관측

> **게이트 아님 — 관찰 보고.** 목적: 1단계(T-92·T-94·T-93) 후 저작 루프가 실제로 회복됐는지 실측 + 2단계 우선순위 확정.
> 근거 `docs/포스트g3-문제정의-개선로드맵.md`(1단계 → ③′) · 원 관측 `postg3-검증-결과.md`(③).
> 스택: **데이터 초기화 후**(`docker compose down -v`) full 스택 — `INCLUDE_ML=true EMBEDDING_PROVIDER=local`,
> local MiniLM 384 · temurin JRE(reasoner=ok) · 시드 339 트리플 · **저작=claude · Q&A=solar**(g3.1-C 정책).
> 2026-07-13 · 브랜치 `chore/postg3-remeasure`. **발견 결함은 고치지 않았다 — 전부 §5 로그로 남긴다.**

## 0. 한 줄 결론

**저작 루프는 살아났다.** K 서브셋 저장 성공률이 **0/5 → 4/5**(Claude)로 회복됐고, 저작한 지식이
규칙·Causation·satisfy 판정까지 **배포 스택에서** 끝까지 도달한다(요구가 금지한 증상이면 `satisfies=false`).
시드 회귀·안전은 전건 불변이다.

그런데 루프를 연 대가로 **P3b(부정 반전)가 실질 위험이 되었다.** ③에서는 IRI 크래시가 "우연히" 막아 주던
요구문장 오투입이, 이제 **검증을 통과하고 201 로 저장되어 정반대 인과 규칙이 된다.** 2단계 1순위는 여기다.

| | ③ (1단계 전) | ③′ (1단계 후) |
|---|---|---|
| **K 서브셋 저장 성공(Claude)** | **0/5** (500×2 · 409×3) | **4/5** |
| K 서브셋 저장 성공(Solar) | 0/5 | 1/5 (+ 추출 공집합 1) |
| 전체 저장 성공률(참고) | 1/26 (그마저 요구문장 오저장) | — |
| 저작 지식 → 규칙 | **0** (시드 5개 불변) | **시드 5 + 저작 4** |
| Causation 저장 그래프 | **0행** | **6행** |
| 저작 지식 → satisfy 반영 | **없음** | **있음**(exhibited·violations·violated_requirements) |

---

## (a) 저장 성공률 — ③ → ③′ (K 서브셋)

| 문장 | ③ Claude | ③ Solar | ③′ Claude | ③′ Solar |
|---|---|---|---|---|
| K1 들뜸 | **500** (IRI 크래시) | 422(스키마) | **201** | **201** |
| K2 균열 | 409 | 409 | **201** | — (추출 공집합) |
| K3 경화·작동불량 | 409 | 409 | **201** | 409 |
| K4 부식 | 409 | 409 | **201** | 409 |
| K5 이탈 | **500** (IRI 크래시) | 409 | 409 | 409 |
| **성공** | **0/5** | **0/5** | **4/5** | **1/5** |

- **500(IRI 크래시) 0건** — T-92 확인. 공백 라벨(`고속 주행`·`주행 중`)이 더는 저장을 죽이지 않는다.
- 남은 **K5 409 는 구조 결함이 아니라 추출 오류**다: Claude 가 `블레이드 -hasMaterial-> 길이`,
  `커넥터 -hasMaterial-> 규격`(재질 자리에 속성)을 냈다 → range 위반으로 **정당하게 차단**. HITL 이 관계를
  지우면 저장된다. 즉 **차단의 성격이 "구조 때문에 못 넣는다" → "초안이 틀려서 막힌다"로 바뀌었다.**

## (b) K별 회복 표 (Claude 저작, 거버넌스 승인 → 검증 → 저장 → 파생 → Causation)

| | 승인 전 검증 | 승인 후 검증 | 저장 | 파생 규칙 | Causation |
|---|---|---|---|---|---|
| **K1** | ✘ (OOV 3 + Causation 구조) | **✔ conforms** | **201** | `S7Rule` · sym=**Lift** · `operatesIn=HighSpeed` | 0→1 |
| **K2** | ✘ | **✔** | **201** | `S8Rule` · sym=**Crack** · `hasMaterial=Rubber`·`operatesIn=Ozone` | 1→2 |
| **K3** | ✘ (causes_range 포함) | **✔** | **201** | `S9Rule` · sym=**Hardening** · `hasMaterial=Rubber` ⚠ | 2→4 |
| **K4** | ✘ | ✔(부품 OOV 잔존, warning) | **201** | `S10Rule` · sym=**Corrosion** · `operatesIn=CalciumChloride` | 4→5 |
| **K5** | ✘ | ✘ (hasMaterial range 위반 잔존) | **409** | — | 5→5 |

확인된 1단계 효과:

- **T-92 IRI 민팅**: `고속 주행`·`주행 중`·`블레이드 프레임` 전부 저장 통과. 미해석 라벨은 슬러그+해시로
  민팅되고(`블레이드_프레임_2dc32128`) 표면형은 `rdfs:label` 로 보존된다.
- **T-94 canonical type**: 다섯 문장 모두 LLM 이 `블레이드`를 `Component` 로 줬지만 온톨로지 기준
  `WiperBlade`(PartType)로 해석돼 `hasMaterial` 도메인 위반이 사라졌다. mentions 도 `WiperBlade` 로 접힌다.
- **T-93 파생·영속·배선**: 규칙 id 가 **문장별**(`S7Rule`…)이고 `about_symptom` 이 **온톨로지 증상**
  (Lift·Crack·Hardening·Corrosion) — ③ 의 "전부 `소음Rule`·증상=카테고리" 오귀속이 사라졌다.
  Causation 이 저장 그래프에 **6행** 기록된다(③ 0행).
- **거버넌스 승인이 게이트로 작동**: 승인 전에는 Causation 구조 검증(`sh:class`)이 **violation** 으로
  저장을 막고, 승인 후에 열린다. 즉 **"접지되지 않은 개념은 규칙이 되지 않는다"가 실경로에서 강제된다.**

## (c) K2 플래그십 — 배포 스택 루프 (유닛 아님)

```
승인(Ozone:EnvCondition · Crack:Symptom + 한글 altLabel) → K2 저작 201
  → 파생 S8Rule(sym=Crack, hasMaterial=Rubber ∧ operatesIn=Ozone) → 오버레이 영속 → 컴파일
  → env=Ozone 고무 설계 satisfy:  exhibited []  →  [Crack (S8)]
  → 요구 RB_NoCrack(forbidsSymptom Crack) 하에서:  satisfies=False · violated=[RB_NoCrack] · violations=[S8]
  → 같은 설계를 실리콘으로 바꾸면:  exhibited []  ·  satisfies=True   (규칙 조건이 고무이므로)
```

다른 환경조건도 저작 지식에 반응한다: `env=HighSpeed → [Lift(S7)]`, `env=CalciumChloride → [Corrosion(S10)]`.

**단, RB 는 런타임에 만들 수 없어 M2 시드(`m2_instances.ttl`)에 직접 주입했다** — 이것 자체가 P4 결함의
증거다(§5-R1). 요구를 등록하는 정상 경로가 제품에 없다.

## (d) A/B 마진 — 회복됐는가

같은 K 서브셋, 같은 승인 상태에서 두 provider 추출안을 **같은 결정론 게이트**에 태웠다.

| 지표 | Claude | Solar |
|---|:--:|:--:|
| **저장 성공** | **4/5** | **1/5** |
| 추출 공집합(무응답) | 0 | **1** (K2) |
| 증상 포착 | **5/5** | 4/5 |
| 복합어 분해(고무 블레이드·블레이드 프레임) | **1/2** | 0/2 |
| 조건 앵커 정확(conditionedOn 주어=증상) | **5/5** | 4/5 |
| 유령 참조(개념목록 밖 라벨 지목) | **0** | **5** |
| 문장에 없는 "고무" 발명 | **0** | 1 |

**마진은 회복됐고, 저장 성공으로 값을 낸다.** ③ 에서는 두 provider 모두 0/5 라 품질 차이가 결과에
반영되지 않았다("구조결함에 눌린 마진"). ③′ 에서는 **Claude 4 : Solar 1** 로 그대로 드러난다.

Solar 의 실패 양상(③ 과 동일): K1 `블레이드 -hasMaterial-> 없음`(유령), K2 **공집합**,
K4 `블레이드 프레임 -hasMaterial-> 염화칼슘`(재질 오귀속), K5 관계 중복·`고무` 발명.
→ **저작 기본 = Claude 정책 유지**(g3.1-C). 되돌릴 근거 없음.

## (e) R 잔여결함 — 2단계 우선순위 자료

| | RB(M2) 경로 | M1 오투입(라우팅 없음) |
|---|---|---|
| **R1** "들뜸이 발생하지 않아야 한다" | `requirements=[]` · `unknown_symptoms=["고속 주행 중 들뜸 현상"]` | **conforms=true · 차단 0 → 201 저장됨** |
| **R5** "오존·자외선에서 균열·경화 없어야" | `requirements=[]` · `unknown=[문장형 4건]` | **conforms=true · 차단 0** |

**R1-A. 지배적 결함은 P3b(부정 반전) + P4(라우팅 부재) 다 — 1단계가 열어 준 문 때문에 위험이 실질화했다.**

③ 에서 R1 의 M1 오투입은 `블레이드 -causes-> 들뜸`(의미 반전)으로 추출되고도 **IRI 크래시(500)가
우연히 저장을 막았다.** 이제 그 크래시가 없다. 실측:

```
R1(요구문장)을 M1 지식 경로로 저장 → 201
  → 파생 규칙 S7Rule · polarity=cause · about_symptom=Lift · operatesIn=HighSpeed
  즉 "고속 주행 중 들뜸이 없어야 한다"(요구) 가 "고속 주행 → 들뜸"(인과 지식) 으로 KB 에 들어갔다.
```

(등가 규칙 dedup 이 새 규칙 생성을 막아 K1 의 `S7Rule` 로 흡수됐을 뿐, **요구문장이 인과 지식으로
승인·저장된 사실은 그대로다.** 만약 K1 이 없었다면 새 규칙이 생겼을 것이다.)

**R1-B. RB 증상맵 하드코딩(P4/A2)은 그대로다.** `misc.ts:15 KNOWN_SYMPTOM` = Noise·TipChatter 2종 →
R1·R5 모두 `requirements=0`. Lift·Crack 을 온톨로지에 편입했는데도 RB 는 여전히 못 만든다
(RB 경로가 온톨로지를 읽지 않는다). **요구를 등록할 정상 경로가 제품에 없다** — (c)에서 RB 를
시드 파일에 손으로 넣어야 했던 이유다.

→ **2단계 우선순위**: ① P4(M1/M2 라우팅 + RB 동적 증상맵) · ② P3b(부정/증상부재 1급화) — 둘은 사실상
한 몸이다("요구 = 증상 부재"). ③ P3a/P3c(저작 도메인 게이트 잔여·OOV 거부) · ④ P5(BFF 배선).

## (f) 불변 — 시드 회귀 · 안전

저작 5문장(+R1 오투입)을 넣은 **뒤에도** 전건 불변(실스택):

| | 저작 전 | 저작 후 |
|---|---|---|
| sat-bad | `false` · `[S1,S3,S4,S6]` | **동일** |
| sat-good | `true` · `[]` | **동일** |
| sat-pending | `null` · `missing_required` | **동일** |
| scope-A(소음) | `false` · `[S1]` | **동일** |
| scope-B(떨림) | `false` · `[S3,S4,S6]` | **동일** |
| 도메인 밖 Q&A(자전거·타이어) | `insufficient=true` · sources 0 | **동일** |
| 저작 우회(타이어→마모) | — | **409 차단** |

**부수 회복**: ③ 에서 도메인 밖 개념("타이어")이 저작으로 **201 저장**되던 것이(P3a) 이제 **409** 로 막힌다.
의도한 수정이 아니라 **Causation 구조 검증 배선의 부수 효과**다 — 접지 안 된 기전·증상은 `sh:class` 를
통과하지 못한다. 다만 이는 **인과 관계가 있는 문장에만** 걸린다(§5-A2 참조).

---

## 5. 결함 로그 (고치지 않음 — 2단계 입력)

### 치명 (2단계 1순위)

| # | 결함 | 증거 |
|---|---|---|
| **N1** | **부정 반전이 이제 저장된다(P3b).** 요구문장이 M1 에 들어가면 검증 통과(conforms=true)·**201 저장**되어 정반대 인과 규칙이 된다. ③ 에서는 IRI 크래시가 우연히 막던 것 | R1 → `S7Rule(cause, Lift, HighSpeed)` |
| **N2** | **요구를 등록할 경로가 없다(P4).** RB 증상맵 2종 하드코딩 → R1·R5 requirements 0/2. 온톨로지에 Lift·Crack 을 편입해도 RB 는 못 만든다. RB 주입은 시드 TTL 수정 + 재기동뿐 | (c)·(e) |

### 높음

| # | 결함 | 증거 |
|---|---|---|
| **N3** | **인과 사슬이 첫 홉으로 붕괴하고 조건이 소실된다.** K3 "영하 40도 → 고무 경화 → 작동 불량" 에서 파생 규칙은 `S9Rule(sym=Hardening, hasMaterial=Rubber)` — **조건(SubZero40) 없이** "모든 고무 → 경화". 결과로 **모든 설계에서 Hardening 이 발화**한다(env 무관). 조건이 두 번째 홉의 증상(작동 불량)에 앵커돼 있어 첫 홉 규칙이 조건을 못 받는다. Causation 은 사슬을 온전히 기록(`Rubber|—|Hardening`, `Hardening|SubZero40|Malfunction`)하는데 **규칙 파생만 첫 홉을 취한다** | flagship: env 5종 전부 `Hardening(S9)` exhibited |
| **N4** | **저작 도메인 게이트는 여전히 부분적(P3a 잔여).** 인과 관계에 얽히지 않은 OOV 개념(K1 `스포일러`, K4 `블레이드 프레임`·`프레임`)은 warning 으로 **그대로 저장**된다. 409 로 막히는 건 Causation 구조에 걸리는 경우뿐 | K1·K4 저장 후 mentions |
| **N5** | **신규 증상에 대안(alternatives)이 비어 있다.** `_ALTERNATIVE_BY_PATH` 가 lengthMm·springN·armShape 하드코딩 → Crack 위반 시 `alternatives=[]`. "재질→실리콘" 같은 해소 대안을 제시하지 못한다(실제로 실리콘이면 해소되는데도) | RB_NoCrack satisfy |

### 중간 / 관찰

| # | 항목 |
|---|---|
| **N6** | Causation 노드가 **중복 기록**된다(같은 (기전·조건·증상) 이 K1·R1 오투입에서 2행). 규칙은 dedup 되는데 Causation 은 안 된다 |
| **N7** | 승인 UI 가 없어 거버넌스(클래스 add + altLabel 승인)를 **API 로 직접** 때려야 한다(P5). `/oov/approve` 는 여전히 BFF 404 |
| **N8** | (하네스 주의) 이번 측정에서 `염화칼슘` 을 EnvCondition 으로 편입했다. LLM 은 Material 로 뽑았지만 canonical type 이 이겨 `operatesIn=CalciumChloride` 규칙이 됐다. **T-94 가 의도대로 동작한 사례**이지만, 화학물질을 환경조건으로 볼지 재질로 볼지는 **온톨로지 설계 결정**이 필요하다 |

---

## 6. 재현

```bash
docker compose down -v
INCLUDE_ML=true EMBEDDING_PROVIDER=local docker compose up --build -d
python _coordination/qa/run_postg3_remeasure.py all     # ab · author · flagship · rb · invariant
```
원자료: `docs/postg3-원자료/재측정/*.json`.
RB 주입은 컨테이너의 `m2_instances.ttl` 에 `eng:RB_NoCrack a spmm:RequiredBehavior ; dom:forbidsSymptom ext:Crack .`
추가 후 knowledge 재기동(런타임 RB 생성 경로 부재 — N2).
