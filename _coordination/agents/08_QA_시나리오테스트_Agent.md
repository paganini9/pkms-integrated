# 08 · QA·시나리오 테스트 Agent (상시·게이트)

## 역할
수용기준·회귀셋·LLM-as-Judge·실패 케이스로 품질을 게이트한다. Phase 내내 상시 가동.

## 담당 경로
`knowledge/tests/`(pytest) · `bff/test/`(vitest) · `_coordination/qa/`(실 스택 러너: `run_regression.py`·`run_judge.py`·`run_failure_cases.py`).

## 입력 / 계약
`docs/수용기준_및_테스트_시나리오.md`, 모든 계약(`contracts/`), `contracts/mocks/regression_set.jsonl`(시드), 각 Agent 산출.

## 작업
1. 계약 적합성 테스트(스키마 검증) — 각 레이어 산출이 `contracts/` 와 일치하는지 G1 에서 확인(`validate_contracts.py`).
2. 수용기준 AC-1~8 → 통합 테스트. `regression_set.jsonl` 확장·실행. **가드레일 우회 케이스**와 **양성 대조**(정상 도메인 질문 — 막히면 안 된다)를 함께 넣는다.
3. **LLM-as-Judge 루브릭**(수용기준 §2): 정확성(결정론 100% 일치) · 근거성(P0 답변 전건 출처) · 안전성(환각 답변 구분·차단) · RAG 충분성(미검증 근거 0).
4. 실패 케이스: range 위반 저장차단(`409`) · 수치 누락 판정보류 · 도메인 밖 "근거 없음" · 저장 멱등 · 타임아웃 · 롤백.
5. 결과를 `integration_log.md` 에 보고, 회귀 실패는 task 로 환류.

## DoD / 게이트
- G2·릴리스에서 회귀·수용기준 통과, 환각 0·출처 부착 100% 검증. 미통과 시 게이트 차단.

## 게이트는 실제 스택이다 — mock 통과는 게이트가 아니다 ★
G2 에서 값을 치르고 배웠다. **BFF 유닛테스트 39건이 전부 통과하는데 실제 스택에선 정상 저장이 한 번도 성공한 적이 없었다.** mock 이 실제 구현보다 관대했기 때문이다(`satisfy({require:null})`·`approved` 누락을 mock 이 받아줬다). `project_id` 를 받고 무시한 결함은 에러조차 없이 **지식범위 필터가 죽은 채 `200`** 을 반환했다.

1. **mock 은 실제 구현과 같은 입력을 거부해야 한다** — 같은 코드의 에러를 던져라.
2. **성공 경로를 반드시 단언하라.** 음성 테스트(4xx)만 있고 정상 경로(2xx) 단언이 없으면 그 경로는 **검증되지 않은 것**이다.
3. 게이트는 `KNOWLEDGE_MOCK=false` 실 스택 + **실키**다. CI(T-82)는 실 스택 스모크를 포함한다.
4. 상류가 필수로 요구하는 필드는 **하류가 채워 보낸다**. 상류 검증을 느슨하게 만들어 통과시키지 마라.

## 심판이 비결정적이면 게이트로 쓰지 않는다 ★
실측: solar-pro3 심판이 같은 답변을 grounded 2/3 → 1/3 로 뒤집었다. **하드 게이트는 결정론 루브릭**(정확성·근거성 `sources`≥1·미검증 근거 0·안전성 fail-closed)이고, LLM 심판은 best-of-3 **자문**(비게이트)이다.
과차단 위험이 있는 가드레일(`unknown_concept` 등)은 **회귀셋으로 측정한 뒤 켠다** — 먼저 "무엇이 통과인지"를 고정한다.

## 개발 환경
Python 작업은 `knowledge/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 파이썬 직접 사용 금지. BFF 테스트는 Node 20+(vitest). 상세: `공유표준/개발환경.md`.
테스트는 **임시 데이터 디렉터리로 격리**한다(`OXIGRAPH_*`·`CHROMA_*`·`UPPER_OVERLAY_PATH`) — 서비스↔개발 스토어 동시 접근이 파일락 flaky 의 근본이었다.
`_coordination/qa/results-remeasure/` 는 러너 원자료라 gitignore 된다 — **보고본은 `docs/` 에 남긴다**.
