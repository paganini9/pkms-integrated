# 08 · QA·시나리오 테스트 Agent (상시·게이트)

## 역할
수용기준·회귀셋·LLM-as-Judge·실패 케이스로 품질을 게이트한다. Phase 내내 상시 가동.

## 담당 경로
`backend/tests/`(unit·integration·regression), 평가 하니스.

## 입력 / 계약
`수용기준_및_테스트_시나리오.md`, 모든 계약, 각 Agent 산출.

## 작업
1. 계약 적합성 테스트(스키마 검증) — 각 레이어 산출이 `contracts/`와 일치하는지 G1에서 확인.
2. 수용기준 AC-* → 통합 테스트. `regression_set.jsonl` 구축·실행.
3. LLM-as-Judge 루브릭(정확성/근거/전이타당성/코인분리/안전·표현/불확실성), 통과 평균 ≥1.5.
4. 실패 케이스(FMP 장애·타임아웃·LLM 오류·면책 누락·루프 미수렴) 자동 검증.
5. 결과를 `integration_log.md`에 보고, 회귀 실패는 task로 환류.

## DoD / 게이트
- G2·릴리스에서 회귀·수용기준 통과, 환각 0·출처 부착 100% 검증. 미통과 시 게이트 차단.

## 인터페이스
- in: 모든 산출. out: 품질 게이트 판정.

## 개발 환경
Python 작업은 `macrolens/backend/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 3.14 직접 사용 금지. 상세: `공유표준/개발환경.md`.
