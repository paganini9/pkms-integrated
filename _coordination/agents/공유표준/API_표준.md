# 공유표준 · API 표준 — 포인터

> **이 문서는 포인터다. 진실원은 `_coordination/contracts/api_standard.md`(v1 freeze).**
> G0 이전 초안이 여기 있었으나, 01 아키텍처 Agent 의 freeze 산출물은 `contracts/` 다(T-02 done).
> 같은 내용을 두 곳에 두면 갈라진다 — 실제로 갈라졌고, 그래서 이 문서를 포인터로 축소했다.
> 변경은 `통신_프로토콜.md` 의 `contract-change` 절차(영향분석 → 승인 → 버전업 → 전체 통지)를 따른다.

| 찾는 것 | 문서 |
|---|---|
| 외부 표면(BFF `/api/v1`) — 엔드포인트·요청·응답·SSE·헤더 | `contracts/api_standard.md` |
| 내부 계약(BFF↔지식서비스) · 레이어 Protocol | `contracts/interface_contracts.md` |
| 에러 코드·HTTP 매핑·사용자 메시지 분리 | `contracts/error_model.md` |
| 계약 결정(CD-1~15) · 불변 원칙 · 버전 이력 | `contracts/README.md` |
| JSON Schema(기계 검증) · mock fixture | `contracts/schemas/` · `contracts/mocks/` |

## 한 줄 요약 (상세는 위 문서)

- 외부에 노출되는 표면은 **BFF `/api/v1` 뿐**이다. 지식서비스(Python)는 내부 전용.
- 판정 필드(`satisfies`·`conforms`·`violations`)는 지식서비스 결정론 결과를 **그대로** 전달한다. BFF 가 재해석하지 않는다.
- 모든 응답 본문(에러 포함)에 `trace_id`(CD-6). 역할 게이트는 `X-Role: engineer|admin`(CD-5).
