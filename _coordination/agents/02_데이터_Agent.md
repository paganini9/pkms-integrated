# 02 · 데이터 Agent

## 역할
와이퍼 도메인 **시드 지식(TTL)** 을 적재·정규화하고 문장·규칙·카테고리의 일관성을 지킨다.

## 담당 경로
`knowledge/ontology/` (`m0.ttl`·`m1_wiper.ttl`·`m2_instances.ttl`·`rules.ttl`·`shapes.ttl`·`lexicon.ttl`·`check_seed.py`).

## 입력 / 계약
`contracts/interface_contracts.md#Store.load_seed`, `contracts/README.md` CD-2·CD-3. SRS·기술설계 §2.

## 작업
1. 시드 TTL 적재: M0(상위 온톨로지)·M1(문장·규칙)·M2(인스턴스)·shapes·rules. **멱등**(named graph 기준 — 재적재 시 트리플 수 불변).
2. **정규화(CD-3)**: `m1_wiper.ttl` 의 `AggravationRule`(S4+S6 묶음) 표기를 `rules.ttl` 기준으로 분리(`SpringRule`·`ArmRule`). **단일 진실원은 `rules.ttl`**(구조화 DesignRule)이며 API 가 노출하는 규칙 id 도 `rules.ttl` 기준이다.
3. 문장 코드 ↔ IRI(CD-2): 코드(`S1`…`S6`)는 `dom:basis`/로컬네임 기준. `dom:sentenceNo` 가 아니다.
4. 일관성 점검 스크립트 `check_seed.py` — 6문장·규칙·카테고리 정합(정규화 전 원본에서 검출되어야 한다).
5. **추론 엣지 생성 질의 보강**: 거동 위계(`has_subbehavior`)로 `/graph?symptom=…` 의 `inferred` 렌더가 실제로 발화하게 한다(AC-4).

## DoD
- 멱등 적재(재적재 시 트리플 수 불변), CD-3 정규화 반영, `check_seed.py` 통과, `GET /categories` 가 카테고리별 문장 수를 정확히 반환.

## 인터페이스
- out: 시드 TTL(→ 06 `Store.load_seed` 가 기동 시 적재). 소비자: 03 RAG(문장 텍스트)·04 추론(규칙). 의존: 계약(G0)만 → P1 병렬.

## 개발 환경
Python 작업은 `knowledge/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 파이썬 직접 사용 금지. 상세: `공유표준/개발환경.md`.
