# 05 · 백엔드·API Agent

## 역할
그래프와 스토어를 FastAPI로 노출한다(SSE). 외부 표면의 단일 통일 지점.

## 담당 경로
`backend/app/api/`(routers·models·exceptions), `backend/app/main.py`.

## 입력 / 계약
`api_standard.md`, `interface_contracts.md#(GraphApp,Store)`, 에러 모델.

## 작업
1. 엔드포인트: `POST /api/v1/chat`(SSE), `GET /health`, `GET|PUT /pins`. 내부 그래프 비노출.
2. 요청/응답 Pydantic 모델 + 입력 검증. `GraphApp.stream()` → SSE 이벤트 1:1 매핑(status/section/token/sources/done/error).
3. 예외 핸들러: AppError 계층→통일 에러 응답(user_message만 노출, trace_id 포함).
4. `main.py` lifespan: env 로드·DB/Chroma 연결·시드, CORS, router include.

## DoD
- API 표준 적합(스키마 검증), SSE 스트리밍 동작, 에러 통일, /health 그린.

## 인터페이스
- in: `GraphApp`(04), `Store`(06). out: HTTP API. 의존: G1 이후(Phase 2).

## RAG 적재 연동
- `main.py` lifespan에서 기동 시 `Retriever.index_incremental()` 1회 호출(파일→Chroma 동기화).
- 브리핑/검색 경로는 `Retriever`가 `ensure_synced()`로 lazy 동기화(05는 호출 보장만, 구현은 03).

## 개발 환경
Python 작업은 `macrolens/backend/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 3.14 직접 사용 금지. 상세: `공유표준/개발환경.md`.
