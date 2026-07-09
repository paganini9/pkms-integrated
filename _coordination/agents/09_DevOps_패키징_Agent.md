# 09 · DevOps·패키징 Agent

## 역할
로컬=Docker 패리티로 패키징하고 서비스 경계·env 배선을 마무리한다.

## 담당 경로
`backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, env 배선.

## 입력 / 계약
기술설계 §2·§8, API 표준(포트), NFR-5/7.

## 작업
1. 서비스 분리: backend(8000)·frontend(8501)·chroma(8001). SQLite는 backend 볼륨.
2. compose: 의존(backend→chroma), env 주입(시크릿 .env, 미커밋), 헬스체크.
3. **패리티 검증**: 코드 수정 없이 로컬·Docker 양쪽 동일 동작.
4. README 실행 절차(제3자 재현) 작성.

## DoD
- `docker compose up`으로 전체 기동, /health 그린, 로컬과 동일 E2E 통과.

## 인터페이스
- in: 전 산출. out: 실행 가능 패키지. 의존: Phase 3.

## 개발 환경
Python 작업은 `macrolens/backend/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 3.14 직접 사용 금지. 상세: `공유표준/개발환경.md`.
