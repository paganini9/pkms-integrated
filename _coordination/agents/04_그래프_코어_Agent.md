# 04 · 추론·코어 Agent (임계 경로)

## 역할
**satisfy 엔진·규칙 컴파일러·reasoner·SHACL 명세검증**을 구현한다. 판정의 심장 — 결정론의 주체다.

## 담당 경로
`knowledge/reasoning/` (`satisfy.py`·`compiler.py`·`rules.py`·`reasoner.py`·`spec_validate.py`·`upper_ontology.py`·`rule_views.py`·`causation.py`·`authoring.py`·`oov.py`·`routes.py`).

## 입력 / 계약
`contracts/interface_contracts.md#(Reasoner,RuleCompiler,SatisfyEngine)` §1·§1.2. `contracts/README.md` CD-1·CD-3·CD-4·CD-7·CD-8·CD-15. 기술설계 §3·§4.

## 작업
1. **satisfy 엔진**(3단계): (1) 정성 subsumption → (2) SHACL 게이트 + 구간 비교기 → (3) 무증상 규칙. `POST /satisfy`.
2. **규칙 컴파일러**: 문장 → 구조화 `DesignRule` → SHACL·인과엣지·사람뷰. **단일 진실원은 `rules.ttl`**. `categories` 필터는 **컴파일 시점**에 적용한다(CD-4 — 판정 후 post-filter 금지, 결과가 달라진다).
3. **reasoner**: HermiT(owlready2), JRE 미가용 시 **owlrl 폴백**. `/reason/consistency`·`/reason/classify`. 두 경로의 판정은 패리티가 맞아야 한다.
4. **명세검증** `/validate/shacl`: range·disjoint·SHACL 제약. severity 는 CD-7 을 따른다 — `violation`(amber = **저장 차단**) vs `warning`(저장 허용: `missing_required`·`unknown_concept`).
5. **시그니처 캐시**: 키 = `sha256(design_canonical + sorted(require) + sorted(categories) + shapes_hash)`. pySHACL shapes 오염에 주의(HTTP 경로에서도 히트해야 한다).
6. 상위 온톨로지(`/upper-ontology/*`)·규칙 조회(`GET /rules`)·영향분석. 승인(`approved:true`) 없는 변경은 `409 GUARDRAIL_BLOCKED`(HITL, 불변원칙 4). 승인된 변경은 영속 오버레이 TTL 에 저장(시드와 분리).
7. **store/rag 는 mock 으로 선행**(계약 준수) → P1 산출 완료 시 실구현 결선. 임계 경로를 보호한다.

## DoD
- fixture 3종 완전 일치, CD-1 정규화(`violation_bases` ↔ `violations`), JRE 없이도 일관성·고의모순 검출, 캐시 히트, 결정론(같은 입력 → 같은 판정).

## 인터페이스
- out: `SatisfyEngine`·`Reasoner`·`RuleCompiler`. 소비자: 05 BFF. 의존: 계약(G0); store/rag 는 mock → 실구현.

## 판정은 LLM 이 하지 않는다 (불변원칙 3) ★
`satisfies`·`conforms`·`violations` 는 **절대 LLM 출력으로 채우지 않는다**. LLM 은 생성(추출 초안·문장 파싱·자연어 답변)만 하고 그건 전부 BFF `aiGateway` 의 일이다. **지식서비스는 LLM 을 호출하지 않는다.**

가드레일은 **도달 가능**(CD-8·CD-12)하고 **우회 불가능**(CD-13)해야 한다:
- CD-8 — `Design` 의 수치가 필수였을 때 결측 요청이 `422` 에서 걸려 **"판정 보류" 경로에 영원히 도달하지 못했다**. `material`·`vehicle` 만 필수, 나머지는 선택 → `satisfies:null`·`pending_reason:"missing_required"`.
- CD-15 — `env` 가 `"Winter"` 로 닫혀 있어 거버넌스로 `Ozone`·`Crack` 을 편입해도 **설계가 그 환경을 표현할 수 없어 지식이 판정에 닿지 못했다**. `Design.env` 는 온톨로지가 아는 `EnvCondition` 의 로컬네임(개방 문자열). 값 검증은 enum 이 아니라 **온톨로지 소속**이 한다.
- `unknown_concept`(CD-7 `warning`) 는 **온톨로지 소속**으로 판정한다(온톨로지 라벨 ∪ 도메인 어휘, 부분일치 금지). 과차단은 도메인 어휘로 해소하되 **회귀셋으로 측정한 뒤 켠다**.

## 개발 환경
Python 작업은 `knowledge/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 파이썬 직접 사용 금지. 상세: `공유표준/개발환경.md`.
호스트에 JRE 가 없으면 owlrl 폴백으로 동작한다(HermiT 경로는 Docker 에서 검증 — knowledge 이미지에 temurin JRE 포함). `/health` 의 `reasoner` 필드로 확인.
