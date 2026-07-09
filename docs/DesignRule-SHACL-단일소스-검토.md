# DesignRule ↔ SHACL 단일 진실 소스 — 검토 + 컴파일러 실증

> 작성일 2026-07-09 · 상태 draft-v0.1 · 열린 항목 "DesignRule↔SHACL 동기화" 검토.
> 결정: **구조화 DesignRule을 단일 진실원(SoT)** 으로 두고, 컴파일러가 SHACL·인과엣지·사람뷰·satisfy를 파생. 컴파일러(`gen_shacl.py`)로 실증 완료.

---

## 1. 문제

같은 6문장 지식이 **손으로 세 곳에** 표현됨 — ① `KnowledgeSentence`(자연어+경량 구조) ② `DesignRule`(메타) ③ `SHACL shape`(실행 게이트). 규칙 하나를 바꾸면(예: SUV 안전길이 599→595) 여러 곳을 고쳐야 하고, 어긋나면 "지식맵 표기 ≠ 검증 동작"의 drift가 발생.

## 2. 방향

| 옵션 | 요지 | 판단 |
|------|------|------|
| **A. 구조화 DesignRule = SoT → SHACL 생성** | 규칙을 기계가독 구조로, SHACL은 빌드 산출 | **채택** |
| B. SHACL = SoT → DesignRule 뷰 추출 | SPARQL을 구조로 역파싱 | ✗ 취약(역파싱 어려움) |
| C. 중립 규칙모델 → 양쪽 생성 | A의 일반형 | A로 수렴 |

## 3. 단일 진실원 설계

**구조화 DesignRule** = 조건들(AND) + 증상 + 극성 + 근거문장. (`rules.ttl`)

**조건 DSL**(작게):
```
Condition = { onPath: 속성경로, op: eq|ne|lt|le|gt|ge|gtPath, val|refList }
  eq/ne   : 값(IRI 또는 리터럴)      예) hasMaterial eq Rubber, armShape eq "simple"
  lt/le/gt/ge : 수치 임계            예) springN lt 10
  gtPath  : 다른 경로의 값과 비교     예) lengthMm gtPath (mountedOn maxSafeLengthMm)
```
6문장 전부(파라미터 비교 포함)를 커버. 표현 밖 케이스는 **raw-SHACL 이스케이프 해치**(그 규칙만 수기 SHACL, 구조 편집기로 round-trip 안 함을 표시).

**한 소스에서 4개 파생**
- (a) **SHACL 게이트** — cause/aggravate 규칙 → NodeShape+SPARQL(CWA 실행).
- (b) **인과 엣지** — 규칙 → `causes/mitigates/aggravates 증상`(지식맵).
- (c) **사람용 규칙 뷰** — 라벨·극성·근거문장.
- (d) **satisfy** — 생성된 SHACL(또는 규칙)로 무증상 판정.

> mitigate 규칙(S2 실리콘)은 원인 규칙의 여집합이라 **게이트 없음**(근거·인과엣지로만 보존). 즉 "실리콘이면 왜 OK?"의 근거는 남되 검증 게이트는 원인 규칙만.

## 4. 컴파일러 실증 (`gen_shacl.py`)

`rules.ttl`(5규칙) → 파생:

```
(a) SHACL 게이트: 4개 생성 → shapes_generated.ttl
     NoiseShape   gateFor=Noise       basis=S1
     ChatterShape gateFor=TipChatter  basis=S3,S5
     SpringShape  gateFor=TipChatter  basis=S4
     ArmShape     gateFor=TipChatter  basis=S6
(b) 인과 엣지(지식맵):
     NoiseRule causes Noise · SiliconeRule mitigates Noise
     ChatterRule causes TipChatter · SpringRule aggravates TipChatter · ArmRule aggravates TipChatter
(c) 사람용 규칙 뷰: 5규칙(극성·근거문장 포함)

생성 SHACL 로 검증 (pySHACL):
  conforms = False
   · 설계 A (고무·600·8N·simple·SUV) — 위반 4건
       [S1] 겨울 + 고무 → 소음
       [S3,S5] 길이 > 차종 안전길이 → 떨림
       [S4] 스프링 압력 < 10N → 떨림 악화
       [S6] 단순 암형상 → 떨림 악화
```

→ **생성된 SHACL이 손으로 쓴 `shapes.ttl`과 동일한 위반을 재현.** 단일 소스에서 SHACL이 나오고, 검증 결과가 동일함을 확인.

## 5. 통합 지점 & 남은 선택

- **shapes.ttl → shapes_generated.ttl**: 손으로 쓴 shapes.ttl은 빌드 산출로 대체. satisfy 파이프라인은 생성 SHACL을 소비(한 줄 연결).
- **S-08(도메인 규칙·SHACL 편집)**: 관리자는 구조화 규칙을 GUI로 편집 → 저장 시 재컴파일. "SHACL 빌더 GUI"가 곧 규칙 편집기.
- **SC-1(지식 입력)**: LLM이 자연어 문장 → **구조화 규칙 후보**를 제안(개념·관계에 더해). 사람이 확인(HITL) 후 컴파일.
- **남은 선택 2**:
  1. LLM이 문장→구조화 규칙을 자동 제안할지(권장) vs 규칙은 관리자만 수기 구조 편집.
  2. 이스케이프 해치 정책 — raw-SHACL 규칙을 어디까지 허용/표시할지.

## 6. 결론
DesignRule↔SHACL drift는 **구조화 DesignRule 단일 소스 + 컴파일러**로 해소된다. 규칙 하나만 고치면 SHACL·지식맵·사람뷰·satisfy가 함께 갱신된다. 실증 컴파일러가 존재하므로 구현 리스크 낮음.
