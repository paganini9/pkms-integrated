import { describe, expect, it, vi } from "vitest";

import { AppError } from "../src/core/errors.js";
import { AIGateway } from "../src/services/ai/gateway.js";
import { MockProvider } from "../src/services/ai/mockProvider.js";
import { CircuitBreaker, isRetryable, TimeoutError, withRetry, withTimeout } from "../src/services/ai/reliability.js";
import type { AIProvider, ExtractionEvent, RequirementDraft, Source } from "../src/services/ai/types.js";

const noSleep = async () => {};

/** 호출 카운터 + 지정 예외를 던지는 스텁 provider. */
function stubProvider(name: "claude" | "gemini", err: () => unknown, counter: { n: number }): AIProvider {
  return {
    name,
    // eslint-disable-next-line require-yield
    async *extract(): AsyncIterable<ExtractionEvent> {
      counter.n++;
      throw err();
    },
    async parseRequirements(): Promise<RequirementDraft[]> {
      counter.n++;
      throw err();
    },
    async answer(_q: string, _c: Source[]): Promise<string> {
      counter.n++;
      throw err();
    },
    async llmOnlyAnswer(_q: string): Promise<string> {
      counter.n++;
      throw err();
    },
    async classify(): Promise<"A" | "B" | "C"> {
      counter.n++;
      throw err();
    },
  };
}

describe("CircuitBreaker", () => {
  it("연속 5실패 → open → 60s 후 half-open", () => {
    let now = 1000;
    const b = new CircuitBreaker(5, 60_000, () => now);
    for (let i = 0; i < 4; i++) b.onFailure();
    expect(b.getState()).toBe("closed");
    b.onFailure(); // 5번째
    expect(b.getState()).toBe("open");
    expect(b.shouldFallback()).toBe(true);
    now += 60_000;
    expect(b.getState()).toBe("half-open");
  });

  it("성공 시 실패 카운터 리셋", () => {
    const b = new CircuitBreaker(3, 1000);
    b.onFailure();
    b.onFailure();
    b.onSuccess();
    b.onFailure();
    b.onFailure();
    expect(b.getState()).toBe("closed");
  });
});

describe("withRetry / withTimeout", () => {
  it("4xx 는 재시도하지 않는다", async () => {
    const err = new AppError("VALIDATION_ERROR", "x", 400);
    expect(isRetryable(err)).toBe(false);
    let calls = 0;
    await expect(
      withRetry(
        async () => {
          calls++;
          throw err;
        },
        { attempts: 2, baseDelayMs: 1, sleep: noSleep },
      ),
    ).rejects.toBe(err);
    expect(calls).toBe(1); // 재시도 없음
  });

  it("5xx/timeout 은 재시도한다 (2회 → 총 3회 시도)", async () => {
    let calls = 0;
    await expect(
      withRetry(
        async () => {
          calls++;
          throw new AppError("LLM_ERROR", "x", 502);
        },
        { attempts: 2, baseDelayMs: 1, sleep: noSleep },
      ),
    ).rejects.toBeInstanceOf(AppError);
    expect(calls).toBe(3);
  });

  it("withTimeout 초과 → TimeoutError", async () => {
    await expect(
      withTimeout(() => new Promise((r) => setTimeout(r, 50)), 5, "slow"),
    ).rejects.toBeInstanceOf(TimeoutError);
  });
});

describe("AIGateway 폴백", () => {
  it("primary 5xx 연속 5회 → CircuitBreaker open → mock 폴백 + providerName mock", async () => {
    const counter = { n: 0 };
    const primary = stubProvider("claude", () => new AppError("LLM_ERROR", "boom", 502), counter);
    const gw = new AIGateway("t", {
      primary,
      mock: new MockProvider(),
      retryAttempts: 0, // 재시도 없이 실패당 1회
      breakerThreshold: 5,
      breakerOpenMs: 60_000,
      sleep: noSleep,
      timeoutMs: 1000,
    });
    // 5회 실패 주입 — 매번 mock 으로 폴백해 답은 나온다. (llmOnlyAnswer 로 신뢰성 경로를 탄다.)
    for (let i = 0; i < 5; i++) {
      const a = await gw.llmOnlyAnswer("q");
      expect(a).toContain("무근거"); // mock 답변
    }
    expect(gw.breakerState()).toBe("open");
    expect(gw.providerName()).toBe("mock");
    expect(counter.n).toBe(5); // primary 는 5회만 시도(재시도 0)
  });

  it("4xx 는 재시도하지 않고 즉시 mock 폴백", async () => {
    const counter = { n: 0 };
    const primary = stubProvider("claude", () => new AppError("VALIDATION_ERROR", "bad", 400), counter);
    const gw = new AIGateway("t", {
      primary,
      mock: new MockProvider(),
      retryAttempts: 2,
      sleep: noSleep,
    });
    const layer = await gw.classify("중형 SUV 안전 길이는?");
    expect(layer).toBe("A"); // mock 키워드 폴백
    expect(counter.n).toBe(1); // 4xx → 재시도 안 함
  });

  it("키 없음(mock 강제) → 전 메서드가 끝까지 동작", async () => {
    const gw = new AIGateway("t", { primary: new MockProvider() });
    expect(gw.providerName()).toBe("mock");
    const drafts = await gw.parseRequirements("겨울철에 소음이 없어야 한다");
    expect(drafts.length).toBeGreaterThan(0);
    const ans = await gw.answer("q", [{ sentence: "S1", text: "..." }]);
    expect(ans).toBeTruthy();
    const events: ExtractionEvent[] = [];
    for await (const e of gw.extract("겨울철 고무 소음")) events.push(e);
    expect(events.some((e) => e.kind === "concept")).toBe(true);
  });
});
