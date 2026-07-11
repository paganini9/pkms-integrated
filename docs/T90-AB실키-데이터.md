# T-90 A/B 실키 데이터 — Solar vs Claude 추출 (T-89·T-91 입력)

> `/api/v1/extraction/ab` 로 두 문장을 Solar(solar-pro3) vs Claude(claude-opus-4-8) 실키 추출. 2026-07-11.
> **측정이지 추정이 아니다**(이슈1 권고). 이 데이터가 T-89(복합어)·T-91(인과) 착수 판단의 근거.

## 입력 1 — "고무 블레이드"

| provider | 개념 | 관계 |
|---|---|---|
| **Solar** | `고무 블레이드 (PartType)` — **원자 복합어** | (없음) |
| **Claude** | `고무 (Material)` · `블레이드 (Component)` — **분해** | `블레이드 —hasMaterial→ 고무` |

## 입력 2 — "겨울철 저온에서 고무 블레이드는 소음이 발생한다"

| provider | 개념 | 관계 |
|---|---|---|
| **Solar** | `고무 블레이드 (Component)` · `겨울철 저온 (EnvCondition)` — 복합어 유지, `소음` 개념 누락 | `고무 블레이드 —causes→ 소음` |
| **Claude** | `겨울철 저온` · `고무 (Material)` · `블레이드 (Component)` · `소음 (Symptom)` — **완전 분해** | `블레이드 —hasMaterial→ 고무` · `블레이드 —causes→ 소음` · `소음 —conditionedOn→ 겨울철 저온` |

## 관찰 (측정된 사실)

1. **Claude 는 복합어를 분해한다** — "고무 블레이드" → `고무(Material)` + `블레이드(Component)` + `hasMaterial`.
   이슈1의 목표(`WiperBlade ⊓ (hasMaterial some Rubber)`)에 가깝다. Solar 는 원자 복합어로 두어 상위 매핑에 실패.
2. **Claude 는 인과를 조건으로 프레임한다** — `소음 —conditionedOn→ 겨울철 저온`. 조건부 인과(이슈2/T-91)의 자연스러운 입력.
3. **Solar 는 6문장 시드 스타일에는 충분**하나 복합어·조건부 인과에서 표층적. → **T-89 컴포지셔널 프레임 + 어휘층**이 Solar 기본 경로를 끌어올리는 방향, Claude 는 escalation·비교용.

## 결론 (스코핑)

- **T-89(복합어·어휘)**: 컴포지셔널 추출 프레임(모델 무관)을 Solar 프롬프트에 넣고, SKOS altLabel 로 `블레이드→WiperBlade`·`고무→Rubber` 를 이관 → Solar 도 분해·매핑. **모델 스위치가 프레임 결함을 덮게 하지 않는다**(이슈1 주의).
- **T-91(인과 reification)**: Claude 의 `conditionedOn` 프레임이 n-ary reified Causation 노드의 실제 입력이 됨을 확인. 6문장 재모델 후 satisfy 회귀 전건 재통과가 게이트.
- **운영 기본은 Solar(무료)**. Claude 는 저작 UI 옵션(유료·opt-in) — A/B 로 "언제 Claude 가 실제로 더 나은가"를 엔지니어가 눈으로 판단.
