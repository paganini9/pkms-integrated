/**
 * AIGateway — Strategy(mock|claude|gemini) + 신뢰성 4종.
 * - 키 없으면 자동 mock (불변원칙 5). AI_MOCK_MODE=true 면 강제 mock.
 * - Timeout(LLM 30s) · Retry(지수 백오프 2회, 4xx 금지) · CircuitBreaker(5실패→60s open→mock 폴백).
 * - 어떤 호출도 최종적으로 mock 으로 폴백해 "끝까지 동작"을 보장한다.
 */
import { config } from "../../core/config.js";
import { log } from "../../core/trace.js";
import { ClaudeProvider } from "./claudeProvider.js";
import { GeminiProvider } from "./geminiProvider.js";
import { MockProvider } from "./mockProvider.js";
import { CircuitBreaker, TimeoutError, withRetry, withTimeout } from "./reliability.js";
import { EmptyContextError, type AIProvider, type ExtractionEvent, type ProviderName, type RequirementDraft, type Source } from "./types.js";

export interface GatewayOpts {
  primary?: AIProvider; // 테스트 주입용
  mock?: AIProvider;
  timeoutMs?: number;
  retryAttempts?: number;
  breakerThreshold?: number;
  breakerOpenMs?: number;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
}

export class AIGateway {
  readonly primary: AIProvider;
  private readonly mock: AIProvider;
  private readonly breaker: CircuitBreaker;
  private readonly timeoutMs: number;
  private readonly retryAttempts: number;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly traceId: string;

  constructor(traceId: string, opts: GatewayOpts = {}) {
    this.traceId = traceId;
    this.mock = opts.mock ?? new MockProvider();
    this.primary = opts.primary ?? pickPrimary(this.mock);
    this.timeoutMs = opts.timeoutMs ?? config.timeouts.llmMs;
    this.retryAttempts = opts.retryAttempts ?? config.retry.attempts;
    this.sleep = opts.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.breaker = new CircuitBreaker(
      opts.breakerThreshold ?? config.breaker.failureThreshold,
      opts.breakerOpenMs ?? config.breaker.openMs,
      opts.now,
    );
  }

  /** 응답에 노출할 provider 이름. 폴백 중이면 mock 을 반영한다. */
  providerName(): ProviderName {
    if (this.primary.name === "mock") return "mock";
    return this.breaker.shouldFallback() ? "mock" : this.primary.name;
  }

  private usingMock(): boolean {
    return this.primary.name === "mock" || this.breaker.shouldFallback();
  }

  /** 비-스트리밍 호출: timeout+retry, 실패 시 breaker 기록 후 mock 폴백. */
  private async call<T>(op: (p: AIProvider) => Promise<T>, label: string): Promise<T> {
    if (this.usingMock()) return op(this.mock);
    try {
      const out = await withRetry(
        () => withTimeout(() => op(this.primary), this.timeoutMs, label),
        { attempts: this.retryAttempts, baseDelayMs: config.retry.baseDelayMs, sleep: this.sleep },
      );
      this.breaker.onSuccess();
      return out;
    } catch (err) {
      this.breaker.onFailure();
      log(this.traceId, "warn", `${label} 실패 → mock 폴백: ${err instanceof TimeoutError ? "timeout" : String(err)}`);
      return op(this.mock);
    }
  }

  /**
   * 스트리밍 추출: 첫 이벤트 이전 실패는 mock 폴백, 이후 실패는 그대로 던진다(부분 결과 보존은 라우트가 처리).
   * 스트림은 재시도하지 않는다(중복 추출 방지, api_standard §5).
   */
  async *extract(text: string): AsyncIterable<ExtractionEvent> {
    if (this.usingMock()) {
      yield* this.mock.extract(text);
      return;
    }
    let yielded = false;
    try {
      // 전체 스트림에 timeout 을 건다.
      const started = Date.now();
      for await (const ev of this.primary.extract(text)) {
        if (Date.now() - started > this.timeoutMs) throw new TimeoutError("extract stream timeout");
        yielded = true;
        yield ev;
      }
      this.breaker.onSuccess();
    } catch (err) {
      this.breaker.onFailure();
      if (yielded) {
        // 부분 결과가 이미 나갔다 — 라우트가 error 이벤트로 종료한다.
        throw err;
      }
      log(this.traceId, "warn", `extract 실패(초기) → mock 폴백`);
      yield* this.mock.extract(text);
    }
  }

  parseRequirements(text: string): Promise<RequirementDraft[]> {
    return this.call((p) => p.parseRequirements(text), "parseRequirements");
  }

  /** CD-14: 검증 답변 전용. 근거가 비면 즉시 throw(reliability·mock 폴백을 거치지 않는다 — 프로그래밍 오류다). */
  answer(question: string, context: Source[]): Promise<string> {
    if (context.length === 0) return Promise.reject(new EmptyContextError());
    return this.call((p) => p.answer(question, context), "answer");
  }

  /** CD-14: 무근거 LLM 단독 답변(환각비교 전용). */
  llmOnlyAnswer(question: string): Promise<string> {
    return this.call((p) => p.llmOnlyAnswer(question), "llmOnlyAnswer");
  }

  classify(question: string): Promise<"A" | "B" | "C"> {
    // 분류 실패는 키워드 폴백(mock)이 있으므로 call 이 mock 으로 넘긴다.
    return this.call((p) => p.classify(question), "classify");
  }

  /** 관측용 — 테스트에서 breaker 상태 확인. */
  breakerState() {
    return this.breaker.getState();
  }
}

function pickPrimary(mock: AIProvider): AIProvider {
  if (config.aiMockMode) return mock;
  if (config.anthropicApiKey) return new ClaudeProvider(config.anthropicApiKey);
  if (config.googleAiApiKey) return new GeminiProvider(config.googleAiApiKey);
  return mock;
}
