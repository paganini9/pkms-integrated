/**
 * 신뢰성 패턴 (interface_contracts.md §6): Timeout · Retry · CircuitBreaker.
 * Idempotency 는 라우트(/extraction/save)에서 draft_id 로 처리한다.
 */
import { AppError, LlmError, LlmTimeout } from "../../core/errors.js";

export class TimeoutError extends Error {}

/** promise 를 timeout 으로 감싼다. 초과 시 TimeoutError. */
export function withTimeout<T>(fn: () => Promise<T>, ms: number, label = "op"): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new TimeoutError(`${label} timed out after ${ms}ms`));
    }, ms);
    fn().then(
      (v) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

/** 4xx 는 재시도하지 않는다 (interface_contracts.md §6). AppError 중 4xx httpStatus 판별. */
export function isRetryable(err: unknown): boolean {
  if (err instanceof TimeoutError) return true;
  if (err instanceof AppError) return err.httpStatus < 400 || err.httpStatus >= 500;
  // 그 외 네트워크·알 수 없는 예외는 재시도 대상.
  return true;
}

export interface RetryOpts {
  attempts: number; // 추가 재시도 횟수 (지수 백오프)
  baseDelayMs: number;
  sleep?: (ms: number) => Promise<void>;
  onRetry?: (attempt: number, err: unknown) => void;
}

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** 지수 백오프 재시도. 4xx 는 즉시 던진다. */
export async function withRetry<T>(fn: () => Promise<T>, opts: RetryOpts): Promise<T> {
  const sleep = opts.sleep ?? defaultSleep;
  let lastErr: unknown;
  for (let attempt = 0; attempt <= opts.attempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      if (!isRetryable(err) || attempt === opts.attempts) throw err;
      opts.onRetry?.(attempt + 1, err);
      await sleep(opts.baseDelayMs * 2 ** attempt);
    }
  }
  throw lastErr;
}

export type BreakerState = "closed" | "open" | "half-open";

/**
 * CircuitBreaker: 연속 N 실패 → open(60s) → half-open 시도.
 * open 동안 호출은 즉시 실패로 처리해 폴백(mock)으로 넘긴다.
 *
 * T-84 — **상태는 BFF 프로세스 메모리(단일 인스턴스 가정)**. 재기동 시 closed 로 초기화되고,
 * 다중 인스턴스면 인스턴스별로 독립 카운트된다. 현재 배포는 단일 BFF 라 문제없다(계약 §6·release
 * 게이트 신뢰성 항목). 다중 인스턴스로 확장 시 공유 스토어(예: Redis)로 외부화해야 한다.
 * 반면 **저장 멱등은 T-83 으로 스토어에 영속**돼 재기동·다중전송에 안전하다(이쪽은 이미 해결).
 */
export class CircuitBreaker {
  private failures = 0;
  private state: BreakerState = "closed";
  private openedAt = 0;

  constructor(
    private readonly threshold: number,
    private readonly openMs: number,
    private readonly now: () => number = () => Date.now(),
  ) {}

  getState(): BreakerState {
    this.refresh();
    return this.state;
  }

  /** open(폴백 필요) 이면 true. */
  shouldFallback(): boolean {
    return this.getState() === "open";
  }

  private refresh(): void {
    if (this.state === "open" && this.now() - this.openedAt >= this.openMs) {
      this.state = "half-open";
    }
  }

  onSuccess(): void {
    this.failures = 0;
    this.state = "closed";
  }

  onFailure(): void {
    this.failures += 1;
    if (this.failures >= this.threshold) {
      this.state = "open";
      this.openedAt = this.now();
    }
  }
}

/** LLM 예외를 계약 에러 코드로 정규화. */
export function toLlmError(err: unknown): AppError {
  if (err instanceof TimeoutError) return new LlmTimeout(err.message);
  if (err instanceof AppError) return err;
  return new LlmError(err instanceof Error ? err.message : String(err));
}
