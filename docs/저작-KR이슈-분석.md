# 설계 분석 — 저작 지식표현(KR) 두 이슈: 복합어 분해 & 조건부 인과(n-ary)

> 배경: 실 MVP 수동검증(재현님)에서 두 근본 KR 이슈 발견. 둘 다 **"자연어 → 논리 온톨로지" 매핑의 고전 난제**다. 현상·원인·처리 방법(확립된 방법론)·개발 반영안.
> 현행 M0 인과모델(확인됨): `ext:conditionedOn` **도메인=FailureBehavior**·range=EnvCondition, `ext:causes/aggravates/mitigates` range=FailureBehavior, `ext:Symptom ⊑ FailureBehavior`, `ext:EnvCondition ⊑ spmm:Attribute`.

---

## 이슈 1 — 복합어 추출·개념 매핑 ("고무 블레이드")

### 현상
Solar가 "고무 블레이드"를 **단일 원자 개념**으로 추출 → 상위 온톨로지 개념에 매핑 실패. '고무'=Material, '블레이드'=Artifact로 **분해하면 각각 매핑 가능**한데 못 함.

### 원인
- 추출 프레임이 복합어를 **분해하지 않음**(표층 그대로).
- 어휘층(SKOS) 부재 → '블레이드'→`dom:WiperBlade`, '고무'→`dom:Rubber` 매핑 근거 없음(현재 라벨은 `rdfs:label` 하나뿐).

### 처리 (방법론)
1. **컴포지셔널 추출 프레임 (모델 무관, 최우선)** — 추출 스키마/프롬프트를 "복합 도메인어 = 핵심명사(head) + 수식(재질/속성) + 관계"로 분해하게. `"고무 블레이드"` → `{artifact: 블레이드→WiperBlade, material: 고무→Rubber, relation: hasMaterial}`, 논리로는 `WiperBlade ⊓ (hasMaterial some Rubber)`. (복합명사 해석 문제 — 통제 도메인에선 소수 컴포지션 패턴 + LLM으로 충분.)
2. **어휘층 (SKOS altLabel, = T-89)** — '블레이드'→WiperBlade, '고무'→Rubber를 `skos:altLabel`로. 검증에서 확인된 `_EXTRA_DOMAIN_VOCAB` 하드셋 이관과 같은 작업.
3. **모델 스위치 (신규 · 인프라 이미 존재)** — AI Gateway에 `claudeProvider.ts`가 **이미 있다**(Phase 2). 엔지니어가 저작 시 provider를 고르게 UI+API 노출(**Solar 기본·무료 / Claude 옵션·유료**). Claude는 일반적으로 구조 분해·지시준수가 강해 복합어 분해가 나아질 개연성이 높지만 — **추정 말고 A/B로 측정**. "두 모델로 추출→diff" 비교 모드는 프로젝트의 환각비교 철학과 동형이라 자연스럽다.

### 주의
- **프레임 개선이 먼저**(모델 무관). 모델 스위치가 프롬프트-프레임 결함을 덮게 하면 안 된다 — 스위치는 escalation·비교용.
- 비용: Claude 유료 vs Solar 무료(프로그램). UI 명시, 기본 Solar. 엔지니어 Claude 사용은 `ANTHROPIC_API_KEY`(앱 env) — Claude Code 개발 인증과는 무관.

---

## 이슈 2 — 조건부 인과의 n-ary 표현 한계 (가장 근본)

### 현상
`"겨울철 저온에서 고무 블레이드는 소음이 발생한다"` = **[블레이드 IN 겨울철] → 소음**. 이를 두 이항 트리플(`블레이드 conditionedOn 겨울철` + `블레이드 causes 소음`)로 쪼개면:
- (a) **의미 분리** — "겨울철에 있다"와 "소음 낸다"가 독립 사실이 되어, "겨울철이라서 소음"이라는 결속이 사라짐.
- (b) **SHACL 위반** — `conditionedOn` 도메인이 FailureBehavior인데 주어가 `고무 블레이드`(PartType) → `ConditionedonDomainShape` 위반 → amber → 저장 차단. 엔지니어는 문장을 못 고침(구조적 한계).

### 근본 원인 — 이항 트리플의 n-ary 한계
"A가 조건 C 하에서 S를 유발한다"는 본질적으로 **3항 관계**다. RDF 이항 트리플로 직접 표현 불가(고전 난제). 현행 M0는 **증상-앵커 이항**(`소음 conditionedOn 겨울철` + `X causes 소음`)으로 우회하는데:
- 6문장엔 되지만, (i) 추출이 주어를 틀리면 위반(지금 케이스), (ii) 한 증상에 **여러 (원인,조건) 맥락**이 붙으면 **바인딩 소실** — 어느 조건이 어느 원인과 짝인지 모름. 재현님이 감지한 "의미 분리"의 정체.

### 처리 (방법론) — 인과의 reification (W3C n-ary 패턴)
인과를 **1급 노드로 재화(reify)**한다. W3C "Defining N-ary Relations on the Semantic Web" 패턴(관계 자체에 속성이 붙는 케이스):

```turtle
:c1 a ext:Causation ;
    ext:hasMechanism    dom:WiperBlade ;    # (⊓ hasMaterial Rubber) — 이슈1 분해 결과
    ext:underCondition  dom:Winter ;         # EnvCondition
    ext:manifestsSymptom dom:Noise .          # Symptom
```

- 한 노드가 **(기전·조건·증상)을 묶음** → 바인딩 보존, 도메인 위반 없음(주어=Causation, 역할별 타입 shape), **OWL 2 EL 안전**(존재 역할), SHACL 검증 용이(Causation shape: 세 역할 필수·타입).
- **SPMM 정합**: SPMM이 이미 Behavior를 reify하는 정신과 일치 — Causation은 "맥락과 함께 잡는 증상 발현"으로 볼 수 있다.
- **satisfy가 오히려 정밀해짐**: "설계 D(고무 WiperBlade)가 프로젝트 조건(겨울)에서 증상 발현?" = D의 기전·조건이 매칭되는 Causation 노드 탐색 → **조건-스코프 정확**. 현행 증상-앵커보다 낫다.
- **단일소스 유지**: 규칙 컴파일러가 문장→구조화규칙→**(Causation 노드 + shape)** 를 방출하도록 확장. 손 SHACL 없음.
- **추출 프레임**: loose 이항이 아니라 **인과 프레임(기전·조건·증상 역할)** 을 타깃(이슈1 컴포지셔널 프레임과 함께).

### 트레이드오프
증상-앵커 이항(단순·현행) vs reified n-ary(정확·다맥락). 6문장 MVP는 전자로 버텼으나 재현님이 정확히 깨지는 케이스를 쳤다. 프로젝트의 논리정합 지향상 **reified n-ary 채택 권장**. 단 M0 인과모델 개정 = **온톨로지+shape+규칙컴파일러+추출+satisfy 정합**이 필요(범위 있음).

---

## 개발 반영 (제안 태스크 · 전부 포스트-g3, g3 릴리스 유효)

| 태스크 | 내용 | 규모 |
|--------|------|:----:|
| **T-89 확장** | 어휘층(SKOS altLabel 이관) + OOV 트리아지 + **복합어 컴포지셔널 추출 프레임** | 중 |
| **T-90 모델 스위치(+A/B)** | provider 선택 UI+API(claudeProvider 존재), Solar 기본·Claude 옵션, "두 모델 추출 diff" 비교 모드 | 소(infra 존재) |
| **T-91 인과 reification** | `ext:Causation` 노드 + 역할 프로퍼티 + shape + 규칙컴파일러·추출·satisfy 정합 + **6문장 재모델** | 대(모델 개정) |

**순서 권고**: **T-89(어휘·복합어) → T-90(모델 스위치, 작음·측정 가능) → T-91(인과 reification, 큼·모델 개정)**. T-90을 앞에 두면 "Claude가 복합어를 실제로 더 잘 푸는가"를 T-91 착수 전에 **데이터로** 확인할 수 있다.

## 리스크
- **T-91 개정이 satisfy 회귀 유발 가능** → 6문장 재모델 후 **기존 satisfy 회귀셋 전건 재통과가 게이트**. 단계적: 모델 설계 → 6문장 재모델 → 컴파일러/추출/satisfy 순.
- 모델 스위치 비용(Claude 유료) → 기본 Solar, 명시적 opt-in, 로그 마스킹.
- 컴포지셔널 추출 **과분해** 위험 → HITL 확인 카드(T-89 트리아지와 같은 UX).

## 한 줄
복합어는 **컴포지셔널 추출 + 어휘층**으로 분해하고(모델 스위치는 escalation·측정), 조건부 인과는 **reified Causation 노드(W3C n-ary 패턴)** 로 바인딩을 보존한다. 둘 다 자연어→논리온톨로지의 고전 난제이며, 기존 단일소스·거버넌스·satisfy에 정합되게 얹는다.
