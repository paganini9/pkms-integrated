/** T-90 — 모델 스위치(provider 라우팅) + A/B diff + 검증 게이트 provider 무관 불변. */
import { describe, expect, it } from "vitest";

import { MockProvider } from "../src/services/ai/mockProvider.js";
import { providerByName } from "../src/services/ai/gateway.js";
import { appFor, postJson, readSse, withServer } from "./util.js";

const withApp = <T>(fn: (base: string) => Promise<T>): Promise<T> => withServer(appFor(), fn);

describe("T-90 provider 라우팅", () => {
  it("stream 기본(provider 미지정): 첫 status 가 stage=provider (요청값 없음)", async () => {
    await withApp(async (base) => {
      const events = await readSse(base, "/api/v1/extraction/stream", { text: "겨울철 저온 고무 소음" });
      expect(events[0].event).toBe("status");
      const d = events[0].data as { stage?: string; requested_provider?: string };
      expect(d.stage).toBe("provider");
      expect(d.requested_provider).toBeUndefined();
      expect(events.at(-1)?.event).toBe("done"); // SSE 계약 유지
    });
  });

  it("stream provider=claude: 키 부재(테스트=mock 모드) → mock 폴백 + 안내(투명)", async () => {
    await withApp(async (base) => {
      const events = await readSse(base, "/api/v1/extraction/stream", { text: "겨울철 고무 소음", provider: "claude" });
      const d = events[0].data as { stage?: string; provider?: string; requested_provider?: string; fallback?: boolean };
      expect(d.stage).toBe("provider");
      expect(d.requested_provider).toBe("claude");
      expect(d.provider).toBe("mock"); // 키 없어 폴백
      expect(d.fallback).toBe(true); // 감추지 않는다
    });
  });

  it("providerByName: mock 모드면 무조건 mock 폴백(그레이스풀)", () => {
    const mock = new MockProvider();
    // 테스트 env 는 AI_MOCK_MODE 기본 → aiMockMode true → 어떤 이름도 mock.
    expect(providerByName("claude", mock).name).toBe("mock");
    expect(providerByName("solar", mock).name).toBe("mock");
    expect(providerByName("mock", mock).name).toBe("mock");
  });
});

describe("T-90 A/B diff", () => {
  it("/extraction/ab: 두 provider 결과를 side-by-side 로 반환", async () => {
    await withApp(async (base) => {
      const { status, body } = await postJson(base, "/api/v1/extraction/ab", { text: "겨울철 저온에서 고무 블레이드는 소음이 발생한다" });
      expect(status).toBe(200);
      const results = (body as { results: Array<{ requested_provider: string; actual_provider: string; concepts: unknown[]; relations: unknown[] }> }).results;
      expect(results).toHaveLength(2);
      expect(results.map((r) => r.requested_provider)).toEqual(["solar", "claude"]); // 기본 쌍
      for (const r of results) {
        expect(Array.isArray(r.concepts)).toBe(true);
        expect(Array.isArray(r.relations)).toBe(true);
      }
    });
  });

  it("/extraction/ab: providers 를 명시하면 그 쌍으로", async () => {
    await withApp(async (base) => {
      const { body } = await postJson(base, "/api/v1/extraction/ab", { text: "고무 블레이드", providers: ["mock", "solar"] });
      const results = (body as { results: Array<{ requested_provider: string }> }).results;
      expect(results.map((r) => r.requested_provider)).toEqual(["mock", "solar"]);
    });
  });
});

describe("T-90 안전 불변 — provider 로 검증 게이트 우회 불가", () => {
  it("save: 서버측 재검증은 provider 를 받지 않는다 — range 위반이면 provider 무관 409", async () => {
    await withApp(async (base) => {
      // 위조된 concepts/relations(고무 causes 겨울철 = causes_range 위반) + approved:true.
      const { status } = await postJson(base, "/api/v1/extraction/save", {
        sentence_text: "경도가 겨울철을 유발한다",
        category: "소음",
        approved: true,
        concepts: [
          { label: "경도", type: "Attribute" },
          { label: "겨울철", type: "EnvCondition" },
        ],
        relations: [{ subject: "경도", predicate: "causes", object: "겨울철" }],
      });
      expect(status).toBe(409); // GUARDRAIL_BLOCKED — 결정론 검증(불변원칙 3), provider 와 무관
    });
  });
});
