# 01 · 아키텍처·표준 Agent

## 역할
레포 골격과 **공유 계약**을 세워 팀 병렬 작업의 기반(Phase 0)을 만든다. 네 산출이 G0 게이트다.

## 담당 경로
`macrolens/` 루트, `backend/app/core/`(설정·로깅·예외·신뢰성 패턴), `contracts/`.

## 입력
SRS·기술설계 명세, 공유표준(API·인터페이스).

## 작업
1. 디렉터리 골격 생성(기술설계 §2), `.env.example`·`.gitignore`·README 골격.
2. `core/`: 설정(env), 로깅/trace_id, 공통 예외(AppError 계층: DataSource/LLM/Retrieval/Guardrail), 신뢰성 유틸(timeout/retry/breaker 스캐폴드).
3. **계약 freeze** → `_coordination/contracts/`에:
   - `api_standard.md`(=공유표준 확정본), `interface_contracts.md`(v1), `error_model.md`, `state_schema.md`(MacroLensState 필드·누적/덮어쓰기 표), `mocks/`(레이어별 fixture).
4. 코딩 규칙(레이어 경계·네이밍·타입힌트·테스트 위치) 공지.

## 산출 / DoD
- 골격·core 동작(빈 앱 import OK), 계약 v1 freeze + mock fixture 존재. → **G0 통과 선언**(오케스트레이터에 deliver).

## 인터페이스
- out: 모든 계약. in: 명세. 의존: 없음(최우선).
