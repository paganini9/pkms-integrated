# 04 · 그래프·코어 Agent (임계 경로)

## 역할
LangGraph State·노드·라우팅과 LLM provider·프롬프트를 구현한다. 런타임 오케스트레이션의 심장.

## 담당 경로
`backend/app/graph/`(state·nodes·routing·build), `backend/app/llm/`(provider·prompts·schemas).

## 입력 / 계약
`state_schema.md`, `interface_contracts.md#(LLM,GraphApp,DataCollector,Retriever,Store)`, 기술설계 §3·§4.

## 작업
1. `MacroLensState` 구현(계약대로 누적/덮어쓰기).
2. 노드 12종(safety·intent_router·trigger_calendar·data_collector·sufficiency_check·rag_retriever·transition_analyzer·sector_ranker·coin_mapper·change_detector·briefing_synthesizer·scenario_analyzer).
3. 라우팅: 완전성·배타성·종료보장 + 검색 루프 상한 N. 안전 분기는 진입점.
4. LLM provider 추상화(Claude 기본/Solar) + 노드별 프롬프트 4요소·temp·structured output.
5. **data/rag/store는 mock으로 선행**(계약 준수) → P1 산출 완료 시 실구현 결선(T-41).
6. 노드·라우팅 단위 테스트(결정성: 같은 입력→같은 경로).

## DoD
- `GraphApp.stream()` 계약 충족, Mock E2E S-A 완주, 가드레일·"근거부족" 분기 동작, 분기 3원칙 통과.

## 인터페이스
- out: `GraphApp`. 소비자: 05 API. 의존: 계약(G0); data/rag/store는 mock→실구현.

## 개발 환경
Python 작업은 `macrolens/backend/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 3.14 직접 사용 금지. 상세: `공유표준/개발환경.md`.

## Solar(Upstage) provider 참고
LLM provider=solar 연동은 `공유표준/참고_solar_upstage.md` 참조. OpenAI 호환 SDK + base_url + `SOLAR_API_KEY`(.env). 키 하드코딩 금지. 사용자가 받은 Agent/Responses+파일 예시는 문서처리용이라 LLM 코어(chat completions)와 구분.
