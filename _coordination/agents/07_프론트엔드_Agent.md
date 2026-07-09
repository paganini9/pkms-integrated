# 07 · 프론트엔드 Agent

## 역할
Streamlit 하이브리드 UI(브리핑 카드 + 대화)를 구현하고 API를 소비한다.

## 담당 경로
`frontend/` (app·components·sse client·state).

## 입력 / 계약
`api_standard.md`(SSE 소비 계약), 기획서 §4(IA·화면), 기술설계 §7.

## 작업
1. IA: 사이드바(시장·핀·깊이·다음 트리거+[지금 브리핑]·면책 상시) / 메인 브리핑 카드(결론·전환 배너·섹터 카드·코인 분리·성장 코너) / 하단 대화.
2. 세션 상태(thread_id·messages·pins·depth·market_scope). SSE 소비로 status/section/token 점진 렌더.
3. 에러 UX: 기술 메시지 대신 다음 행동 안내. 빈 상태 예시 질문.
4. 표시 순서 결론→근거→주의·불확실성→출처. 색은 방향에만 절제.
5. **mock API 서버로 선행** 가능 → 실 API(05) 결선.

## DoD
- E2E: 트리거→브리핑 스트리밍→근거·출처 표시, 핀 즉시 반영, 에러 UX 동작.

## 인터페이스
- in: HTTP API(05). 의존: API 표준(G0)으로 선행, 05 완료 후 결선.
