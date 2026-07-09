/**
 * 공통 예외 — `_coordination/contracts/error_model.md` v1 구현.
 * 응답 직렬화는 errorHandler 미들웨어 한 곳에서만 한다.
 */
export type ErrorCode =
  | "VALIDATION_ERROR"
  | "GUARDRAIL_BLOCKED"
  | "BUILTIN_LOCKED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "LLM_ERROR"
  | "LLM_TIMEOUT"
  | "STORE_ERROR"
  | "REASONER_ERROR"
  | "REASONER_TIMEOUT"
  | "RAG_ERROR"
  | "KNOWLEDGE_UNAVAILABLE"
  | "INTERNAL";

export class AppError extends Error {
  constructor(
    public readonly code: ErrorCode,
    public readonly userMessage: string,
    public readonly httpStatus: number,
    /** 내부 원인 — 로그에만. 응답 본문에 넣지 않는다. */
    public readonly internal?: string,
    public readonly details?: Record<string, unknown>,
  ) {
    super(internal ?? userMessage);
    this.name = new.target.name;
  }

  toBody(traceId: string) {
    return {
      code: this.code,
      user_message: this.userMessage,
      trace_id: traceId,
      ...(this.details ? { details: this.details } : {}),
    };
  }
}

export class ValidationError extends AppError {
  constructor(internal?: string, details?: Record<string, unknown>) {
    super("VALIDATION_ERROR", "입력값을 확인해 주세요.", 422, internal, details);
  }
}

export class GuardrailBlocked extends AppError {
  constructor(internal?: string) {
    super(
      "GUARDRAIL_BLOCKED",
      "명세 위반이 남아 있어 저장할 수 없습니다. 경고를 해소한 뒤 승인해 주세요.",
      409,
      internal,
    );
  }
}

export class Forbidden extends AppError {
  constructor(internal?: string) {
    super("FORBIDDEN", "관리자 권한이 필요합니다.", 403, internal);
  }
}

export class LlmError extends AppError {
  constructor(internal?: string) {
    super("LLM_ERROR", "AI 응답에 실패했습니다. 다시 시도해 주세요.", 502, internal);
  }
}

export class LlmTimeout extends AppError {
  constructor(internal?: string) {
    super("LLM_TIMEOUT", "AI 응답이 지연됩니다. 다시 시도해 주세요.", 504, internal);
  }
}

export class KnowledgeUnavailable extends AppError {
  constructor(internal?: string) {
    super("KNOWLEDGE_UNAVAILABLE", "지식 서비스에 연결할 수 없습니다.", 503, internal);
  }
}
