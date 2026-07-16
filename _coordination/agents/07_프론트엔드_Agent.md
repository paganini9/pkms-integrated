# 07 · 프론트엔드 Agent

## 역할
**React 화면**(지식입력·설계검증·Q&A/환각비교·지식맵)을 구현하고 BFF `/api/v1` 을 소비한다.

## 담당 경로
`frontend/src/` (`screens/`·`components/`·`api/`·`types/`·`mocks/`). React 18 · Vite · TS · Tailwind · Cytoscape.

## 입력 / 계약
`contracts/api_standard.md`(외부 표면·SSE 소비 계약·공통 타입), `contracts/mocks/`(선행용 fixture). 기획서 §4(IA·화면), 기술설계 §7.

## 작업
1. **핵심 3화면**: 지식입력(추출 SSE → 검증 → HITL 승인 저장) · 설계검증(satisfy 3단계 결과·판정 보류) · Q&A(A/B/C + **환각비교**).
2. **지식맵**(Cytoscape): `GET /graph` 렌더. **`inferred:true` 엣지는 점선**으로 구분한다(AC-4).
3. **SSE 소비**: 이벤트 순서 status* → (section|token|sources)* → done. `error` 는 어디서든 종료. 부분 결과 허용(done 전 error 시 그때까지 렌더 유지 + 안내).
4. **에러 UX**: 기술 메시지 대신 다음 행동 안내(`user_message` 만 노출). 빈 상태 예시 질문.
5. **amber 승인 차단(CD-7)**: `severity:"violation"` 항목이 하나라도 있으면 **승인 버튼 비활성화**. amber 는 "치명적이지 않아 보이는 색"이 아니라 **"고쳐야 저장된다"는 신호**다. `warning`(`missing_required`·`unknown_concept`)은 정보 표시하되 저장을 막지 않는다.
6. 표시 순서: 결론 → 근거 → 주의·불확실성 → 출처. 관리자 표면은 `X-Role: admin` 게이트(CD-5).
7. **mock API 로 선행** 가능 → 실 BFF 결선. `contracts/mocks/` 를 서빙하는 vite 프록시 or msw.

## DoD
- E2E: 지식입력 SSE → 검증 → 승인 저장, satisfy 판정 렌더, Q&A 근거·출처 표시, `inferred` 점선 렌더, 에러 UX·amber 차단 동작. → **G2**

## 인터페이스
- in: BFF `/api/v1`(05). 의존: API 표준(G0)으로 선행, 05 완료 후 결선.

## 판정 보류를 확정 답변처럼 그리지 않는다 ★
`satisfies: null`(CD-8 판정 보류)은 ✅ 도 ⛔ 도 아니다. **무엇이 없어서 판정을 못 하는지**(`pending_reason`·`missing_required`)를 보여준다. 부분 정보로 확정 판정을 렌더하면 CD-8·CD-14 가 서버에서 막아낸 것을 화면에서 되살리는 셈이다.
`insufficient_evidence:true` 면 `sources` 는 빈 배열이다 — 출처 UI 를 억지로 채우지 않는다.

## 개발 환경
호스트 **Node 20+** 를 그대로 쓴다(venv 무관). `npm run dev` → http://localhost:5173, `/api` → BFF 4000 프록시. 상세: `공유표준/개발환경.md`.
