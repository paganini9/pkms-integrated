# 계약 · 에러 모델 — v1 freeze

> 내부 원인과 사용자 메시지를 **분리**한다. 본문에는 `user_message`만, 원인은 로그(`trace_id`로 결합)에만.
> 근거: `docs/기술_설계_명세서.md` §6 · `docs/수용기준_및_테스트_시나리오.md` §4.

## 1. 응답 형태 (BFF·지식서비스 공통)

```json
{ "code": "REASONER_ERROR",
  "user_message": "설계 검증이 오래 걸립니다. 잠시 후 다시 시도해 주세요.",
  "trace_id": "0f9c...",
  "details": { "field": "design.spring_n" }   // 선택. VALIDATION_ERROR에서만 필드 경로 노출
}
```
- `user_message`는 **한글 · 다음 행동 안내**. 스택트레이스·내부 IRI·SQL/SPARQL 문자열 금지.
- SSE에서는 `event: error`의 `data`가 같은 형태다.

## 2. 코드 · HTTP 매핑

| code | HTTP | 발생 | 사용자 메시지(기본) | 폴백 |
|---|:--:|---|---|---|
| `VALIDATION_ERROR` | 422 | 입력 스키마 위반(zod·Pydantic) | "입력값을 확인해 주세요." | — |
| `GUARDRAIL_BLOCKED` | 409 | 미승인 저장·검증 위반 상태 저장 시도 | "명세 위반이 남아 있어 저장할 수 없습니다. 경고를 해소한 뒤 승인해 주세요." | 저장 차단(HITL) |
| `BUILTIN_LOCKED` | 400 | builtin 개념·관계 삭제/수정 시도 | "기본 개념은 삭제할 수 없습니다." | — |
| `FORBIDDEN` | 403 | 비관리자가 admin 표면 접근 | "관리자 권한이 필요합니다." | — |
| `NOT_FOUND` | 404 | 프로젝트·문장·규칙 없음 | "대상을 찾을 수 없습니다." | — |
| `LLM_ERROR` | 502 | provider 오류·응답 파싱 실패 | "AI 응답에 실패했습니다. 다시 시도해 주세요." | **Mock 폴백** |
| `LLM_TIMEOUT` | 504 | LLM 타임아웃 | "AI 응답이 지연됩니다. 다시 시도해 주세요." | Retry → Mock 폴백 |
| `STORE_ERROR` | 500 | 트리플/벡터 저장·롤백 | "저장에 실패했습니다. 변경사항은 반영되지 않았습니다." | 롤백(원자성) |
| `REASONER_ERROR` | 500 | HermiT/pySHACL 실패 | "검증 엔진 오류입니다. 잠시 후 다시 시도해 주세요." | owlrl 폴백(가능 시) |
| `REASONER_TIMEOUT` | 504 | 추론 지연 | "검증이 오래 걸립니다. 잠시 후 다시 시도해 주세요." | 시그니처 캐시 |
| `RAG_ERROR` | 500 | 임베딩·Chroma 실패 | "검색에 실패했습니다." | mock 임베딩 |
| `KNOWLEDGE_UNAVAILABLE` | 503 | 지식서비스 도달 불가 | "지식 서비스에 연결할 수 없습니다." | `/health` degraded |
| `INTERNAL` | 500 | 그 외 | "일시적인 오류입니다." | — |

## 3. "에러가 아닌" 케이스 (200으로 응답)

명세상 **정상 흐름**이므로 에러로 만들지 않는다. 프론트가 상태로 렌더한다.

| 상황 | 응답 | 필드 |
|---|:--:|---|
| 추출 range/disjoint 위반 | 200 | `conforms:false`, `violations[].severity:"violation"` → **amber** + 승인 버튼 비활성 (AC-1 · CD-7) |
| satisfy 불만족 | 200 | `satisfies:false`, `violations`, `alternatives` (AC-2) |
| satisfy 수치 누락 | 200 | `satisfies:null`, `pending_reason:"missing_required"` — 판정 보류 |
| 도메인 밖 질의 | 200 | `insufficient_evidence:true`, `verified_answer.text` = "명세 근거 없음" 명시 |
| 지식서비스 degraded | 200 | `/health` `status:"degraded"` |

> **저장은 다르다.** `severity:"violation"`이 남은 상태의 `/extraction/save`는 `409 GUARDRAIL_BLOCKED`로 차단한다.

## 4. 로깅 · 마스킹

- 로그 라인에 `trace_id`·`code`·내부 원인(스택·응답 본문). **API 키는 `sk-***`로 마스킹**, 원문 금지.
- `satisfy`의 `justification`은 감사 로그로 별도 보존(NFR 관측성).
- 지식서비스 → BFF 에러는 `code`를 보존해 그대로 전파한다(BFF가 `INTERNAL`로 뭉개지 않는다). 단 `KNOWLEDGE_UNAVAILABLE`은 BFF가 생성.

## 5. 예외 클래스 (구현 가이드)

```python
# knowledge/schemas/errors.py — 01 소유
class AppError(Exception):
    code: str; http_status: int; user_message: str
class ValidationError(AppError):  ...  # 422
class GuardrailBlocked(AppError):  ... # 409
class StoreError(AppError):  ...       # 500
class ReasonerError(AppError):  ...    # 500
class RagError(AppError):  ...         # 500
```
```ts
// bff/src/core/errors.ts — 01 소유
export class AppError extends Error { constructor(public code: ErrorCode, public userMessage: string, public httpStatus: number) {} }
export class LlmError extends AppError {}
export class KnowledgeUnavailable extends AppError {}
```
FastAPI `exception_handler` / Express `errorHandler` 미들웨어가 위 형태로 직렬화한다. **핸들러 밖에서 응답 본문을 만들지 않는다.**
