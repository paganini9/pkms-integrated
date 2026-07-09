# 공유표준 · API 표준 (통일 규칙)

> 모든 HTTP 표면은 이 표준을 따른다. 01 아키텍처 Agent가 freeze, 05 백엔드가 구현, 07 프론트가 소비.
> 기준: `기술_설계_명세서.md §6`.

## 1. 공통 규약
- Base path: `/api/v1` (버저닝 필수). 내부 그래프 구조 비노출.
- 요청/응답 본문: JSON(UTF-8). 모델은 Pydantic, 입력 검증 명시(min/max length 등).
- 모든 응답에 `trace_id` 포함(관측성). 시각은 ISO-8601 UTC.
- 인증: MVP 미적용(로컬). 헤더 `X-Thread-Id` 선택.

## 2. 엔드포인트
### `POST /api/v1/chat` (SSE)
요청:
```json
{ "thread_id": "uuid?", "message": "string(1..2000)",
  "mode": "briefing|whatif|deepdive?",
  "market_scope": ["KR","US"]?, "depth": "conclusion|evidence|background?" }
```
응답: `text/event-stream`. 이벤트 타입(필수 통일):
```
event: status   data: {"stage":"collect|analyze|retrieve|synthesize","msg":"..."}
event: section  data: {"kind":"sector|coin|change|ranking","payload":{...}}
event: token    data: {"text":"..."}            # 스트리밍 본문 조각
event: sources  data: {"items":[{"title","url","ref"}]}
event: done     data: {"thread_id","summary","trace_id"}
event: error    data: {"code","user_message","trace_id"}
```

### `GET /api/v1/health`
`200 {"status":"ok","llm_provider":"claude|solar","chroma":"ok","db":"ok"}`

### `GET /api/v1/pins` · `PUT /api/v1/pins`
`{"pinned_sectors":["반도체","2차전지","AI/SW"]}` (영속화).

## 3. 에러 응답 (HTTP + body 통일)
```json
{ "code": "DATA_SOURCE_ERROR|LLM_ERROR|RETRIEVAL_ERROR|GUARDRAIL_BLOCKED|VALIDATION_ERROR|INTERNAL",
  "user_message": "사용자용 안내(다음 행동)", "trace_id": "..." }
```
- 4xx: VALIDATION_ERROR(422), GUARDRAIL_BLOCKED(200 안전응답 권장 or 403).
- 5xx: DATA_SOURCE/LLM/RETRIEVAL/INTERNAL. 내부 원인은 로그에만, 본문엔 user_message만.

## 4. SSE 소비 계약(프론트)
- 이벤트 순서: status* → (section|token|sources)* → done. error는 어디서든 종료.
- 부분 결과 허용: done 전 error 시 그때까지 렌더 유지 + 안내.
