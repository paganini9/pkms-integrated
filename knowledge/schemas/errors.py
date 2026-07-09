"""공통 예외 계층 — `_coordination/contracts/error_model.md` v1 구현.

내부 원인(`internal`)은 로그에만, 응답 본문에는 `user_message`만 나간다.
응답 직렬화는 main.py 의 exception_handler 한 곳에서만 한다.
"""
from typing import Any


class AppError(Exception):
    code: str = "INTERNAL"
    http_status: int = 500
    user_message: str = "일시적인 오류입니다."

    def __init__(
        self,
        internal: str = "",
        *,
        user_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(internal or self.user_message)
        self.internal = internal
        if user_message:
            self.user_message = user_message
        self.details = details

    def to_body(self, trace_id: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "code": self.code,
            "user_message": self.user_message,
            "trace_id": trace_id,
        }
        if self.details:
            body["details"] = self.details
        return body


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    http_status = 422
    user_message = "입력값을 확인해 주세요."


class GuardrailBlocked(AppError):
    code = "GUARDRAIL_BLOCKED"
    http_status = 409
    user_message = "명세 위반이 남아 있어 저장할 수 없습니다. 경고를 해소한 뒤 승인해 주세요."


class BuiltinLocked(AppError):
    code = "BUILTIN_LOCKED"
    http_status = 400
    user_message = "기본 개념은 삭제할 수 없습니다."


class Forbidden(AppError):
    code = "FORBIDDEN"
    http_status = 403
    user_message = "관리자 권한이 필요합니다."


class NotFound(AppError):
    code = "NOT_FOUND"
    http_status = 404
    user_message = "대상을 찾을 수 없습니다."


class StoreError(AppError):
    code = "STORE_ERROR"
    http_status = 500
    user_message = "저장에 실패했습니다. 변경사항은 반영되지 않았습니다."


class ReasonerError(AppError):
    code = "REASONER_ERROR"
    http_status = 500
    user_message = "검증 엔진 오류입니다. 잠시 후 다시 시도해 주세요."


class ReasonerTimeout(AppError):
    code = "REASONER_TIMEOUT"
    http_status = 504
    user_message = "검증이 오래 걸립니다. 잠시 후 다시 시도해 주세요."


class RagError(AppError):
    code = "RAG_ERROR"
    http_status = 500
    user_message = "검색에 실패했습니다."
