# 01 · 아키텍처·표준 Agent

## 역할
레포 골격과 **공유 계약**을 세워 팀 병렬 작업의 기반(Phase 0)을 만든다. 네 산출이 G0 게이트다.

## 담당 경로
`pkms-integrated/` 루트(3서비스 골격: `frontend`·`bff`·`knowledge`), `knowledge/core/`(설정·로깅·예외·신뢰성 패턴), `_coordination/contracts/`.

## 입력
SRS·기술설계 명세(`docs/`), 수용기준.

## 작업
1. 디렉터리 골격 생성(기술설계 §2), `.env.example`·`.gitignore`·README 골격. 3서비스 경계(불변원칙 1)를 구조로 못박는다.
2. `core/`: 설정(env), 로깅/trace_id(CD-6), 공통 예외(AppError 계층), 신뢰성 유틸(timeout/retry/breaker 스캐폴드), `core/mocks.py`.
3. **계약 freeze** → `_coordination/contracts/`에:
   - `api_standard.md`(BFF 외부 `/api/v1`), `interface_contracts.md`(내부 계약 + 레이어 Protocol), `error_model.md`,
     `schemas/*.json`(기계 검증), `mocks/*.json`(레이어별 fixture), `validate_contracts.py`.
   - 명세가 갈리는 지점은 **계약 결정(CD-*)** 으로 확정해 `contracts/README.md` 에 근거와 함께 남긴다.
4. 코딩 규칙(레이어 경계·네이밍·타입힌트·테스트 위치) 공지.

## 산출 / DoD
- 3서비스 typecheck/import OK, BFF↔지식 health 왕복. 계약 v1 freeze + `validate_contracts.py` 통과 + mock fixture 존재. → **G0 통과 선언**(오케스트레이터에 deliver).

## 인터페이스
- out: 모든 계약. in: 명세. 의존: 없음(최우선).

## 계약 변경 통제
freeze 이후 계약은 **무단 변경 금지**. 변경은 `통신_프로토콜.md` 의 `contract-change` 절차(영향분석 → 승인 → 버전업 → 전체 통지)를 따르고 `contracts/README.md` §0 버전 이력에 남긴다.
`공유표준/API_표준.md`·`공유표준/인터페이스_계약.md` 는 **포인터**다 — 계약 내용을 그쪽에 복제하지 않는다(두 진실원은 반드시 갈라진다).
